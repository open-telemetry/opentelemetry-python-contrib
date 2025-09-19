# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# pylint: disable=import-outside-toplevel,no-name-in-module
import importlib
import logging
import sys
import threading
from dataclasses import asdict
from typing import Any
from unittest import TestCase
from unittest.mock import MagicMock, patch

import fsspec

from opentelemetry._logs import LogRecord
from opentelemetry.test.test_base import TestBase
from opentelemetry.util.genai import types
from opentelemetry.util.genai._fsspec_upload.fsspec_hook import (
    FsspecUploadHook,
)
from opentelemetry.util.genai.upload_hook import (
    _NoOpUploadHook,
    load_upload_hook,
)

# Use MemoryFileSystem for testing
# https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.implementations.memory.MemoryFileSystem
BASE_PATH = "memory://"


@patch.dict(
    "os.environ",
    {
        "OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK": "fsspec",
        "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH": BASE_PATH,
    },
    clear=True,
)
class TestFsspecEntryPoint(TestCase):
    def test_fsspec_entry_point(self):
        self.assertIsInstance(load_upload_hook(), FsspecUploadHook)

    def test_fsspec_entry_point_no_fsspec(self):
        """Tests that the a no-op uploader is used when fsspec is not installed"""

        from opentelemetry.util.genai import _fsspec_upload

        # Simulate fsspec imports failing
        with patch.dict(
            sys.modules,
            {"opentelemetry.util.genai._fsspec_upload.fsspec_hook": None},
        ):
            importlib.reload(_fsspec_upload)
            self.assertIsInstance(load_upload_hook(), _NoOpUploadHook)


MAXSIZE = 5
FAKE_INPUTS = [
    types.InputMessage(
        role="user",
        parts=[types.Text(content="What is the capital of France?")],
    ),
]
FAKE_OUTPUTS = [
    types.OutputMessage(
        role="assistant",
        parts=[types.Text(content="Paris")],
        finish_reason="stop",
    ),
]
FAKE_SYSTEM_INSTRUCTION = [types.Text(content="You are a helpful assistant.")]


class TestFsspecUploadHook(TestCase):
    def setUp(self):
        self._fsspec_patcher = patch(
            "opentelemetry.util.genai._fsspec_upload.fsspec_hook.fsspec"
        )
        self.mock_fsspec = self._fsspec_patcher.start()
        self.hook = FsspecUploadHook(
            base_path=BASE_PATH,
            max_size=MAXSIZE,
        )

    def tearDown(self) -> None:
        self.hook.shutdown()
        self._fsspec_patcher.stop()

    def test_shutdown_no_items(self):
        self.hook.shutdown()

    def test_upload_then_shutdown(self):
        self.hook.upload(
            inputs=FAKE_INPUTS,
            outputs=FAKE_OUTPUTS,
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
        )
        # all items should be consumed
        self.hook.shutdown()

        self.assertEqual(
            self.mock_fsspec.open.call_count,
            3,
            "should have uploaded 3 files",
        )

    def test_upload_blocked(self):
        unblock_upload = threading.Event()

        def blocked_upload(*args: Any):
            unblock_upload.wait()
            return MagicMock()

        self.mock_fsspec.open.side_effect = blocked_upload

        # fill the queue
        for _ in range(MAXSIZE):
            self.hook.upload(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
            )

        self.assertLessEqual(
            self.mock_fsspec.open.call_count,
            MAXSIZE,
            f"uploader should only be called {MAXSIZE=} times",
        )

        with self.assertLogs(level=logging.WARNING) as logs:
            self.hook.upload(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
            )

        self.assertIn(
            "fsspec upload queue is full, dropping upload", logs.output[0]
        )

        unblock_upload.set()

    def test_failed_upload_logs(self):
        def failing_upload(*args: Any) -> None:
            raise RuntimeError("failed to upload")

        self.mock_fsspec.open = MagicMock(wraps=failing_upload)

        with self.assertLogs(level=logging.ERROR) as logs:
            self.hook.upload(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
            )
            self.hook.shutdown()

        self.assertIn("fsspec uploader failed", logs.output[0])

    def test_upload_after_shutdown_logs(self):
        self.hook.shutdown()
        with self.assertLogs(level=logging.INFO) as logs:
            self.hook.upload(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
            )
        self.assertEqual(len(logs.output), 1)
        self.assertIn(
            "attempting to upload file after FsspecUploadHook.shutdown() was already called",
            logs.output[0],
        )


class FsspecUploaderTest(TestCase):
    def test_upload(self):
        FsspecUploadHook._do_upload(
            "memory://my_path",
            lambda: [asdict(fake_input) for fake_input in FAKE_INPUTS],
        )

        with fsspec.open("memory://my_path", "r") as file:
            self.assertEqual(
                file.read(),
                '[{"role":"user","parts":[{"content":"What is the capital of France?","type":"text"}]}]',
            )


class TestFsspecUploadHookIntegration(TestBase):
    def setUp(self):
        super().setUp()
        self.hook = FsspecUploadHook(base_path=BASE_PATH)

    def tearDown(self):
        super().tearDown()
        self.hook.shutdown()

    def assert_fsspec_equal(self, path: str, value: str) -> None:
        with fsspec.open(path, "r") as file:
            self.assertEqual(file.read(), value)

    def test_upload_completions(self):
        tracer = self.tracer_provider.get_tracer(__name__)
        log_record = LogRecord()

        with tracer.start_as_current_span("chat mymodel") as span:
            self.hook.upload(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
                span=span,
                log_record=log_record,
            )
        self.hook.shutdown()

        finished_spans = self.get_finished_spans()
        self.assertEqual(len(finished_spans), 1)
        span = finished_spans[0]

        # span attributes, log attributes, and log body have refs
        for attributes in [
            span.attributes,
            log_record.attributes,
        ]:
            for ref_key in [
                "gen_ai.input.messages_ref",
                "gen_ai.output.messages_ref",
                "gen_ai.system_instructions_ref",
            ]:
                self.assertIn(ref_key, attributes)

        self.assert_fsspec_equal(
            span.attributes["gen_ai.input.messages_ref"],
            '[{"role":"user","parts":[{"content":"What is the capital of France?","type":"text"}]}]',
        )
        self.assert_fsspec_equal(
            span.attributes["gen_ai.output.messages_ref"],
            '[{"role":"assistant","parts":[{"content":"Paris","type":"text"}],"finish_reason":"stop"}]',
        )
        self.assert_fsspec_equal(
            span.attributes["gen_ai.system_instructions_ref"],
            '[{"content":"You are a helpful assistant.","type":"text"}]',
        )

    def test_stamps_empty_log(self):
        log_record = LogRecord()
        self.hook.upload(
            inputs=FAKE_INPUTS,
            outputs=FAKE_OUTPUTS,
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
            log_record=log_record,
        )

        # stamp on both body and attributes
        self.assertIn("gen_ai.input.messages_ref", log_record.attributes)
        self.assertIn("gen_ai.output.messages_ref", log_record.attributes)
        self.assertIn("gen_ai.system_instructions_ref", log_record.attributes)

    def test_upload_bytes(self) -> None:
        log_record = LogRecord()
        self.hook.upload(
            inputs=[
                types.InputMessage(
                    role="user",
                    parts=[
                        types.Text(content="What is the capital of France?"),
                        {"type": "generic_bytes", "bytes": b"hello"},
                    ],
                )
            ],
            outputs=FAKE_OUTPUTS,
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
            log_record=log_record,
        )
        self.hook.shutdown()

        self.assert_fsspec_equal(
            log_record.attributes["gen_ai.input.messages_ref"],
            '[{"role":"user","parts":[{"content":"What is the capital of France?","type":"text"},{"type":"generic_bytes","bytes":"aGVsbG8="}]}]',
        )
