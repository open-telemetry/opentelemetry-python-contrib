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


# pylint: disable=no-name-in-module
import logging
import threading
import time
from contextlib import contextmanager
from platform import python_implementation
from typing import Any
from unittest import TestCase, skipIf
from unittest.mock import ANY, MagicMock, patch

import fsspec

from opentelemetry._logs import LogRecord
from opentelemetry.test.test_base import TestBase
from opentelemetry.util.genai import types
from opentelemetry.util.genai._upload.completion_hook import (
    UploadCompletionHook,
)

# Use MemoryFileSystem for testing
# https://filesystem-spec.readthedocs.io/en/latest/api.html#fsspec.implementations.memory.MemoryFileSystem
BASE_PATH = "memory://"
MAXSIZE = 5
FAKE_INPUTS = [
    types.InputMessage(
        role="user",
        parts=[types.Text(content="What is the capital of France?")],
    ),
    types.InputMessage(
        role="assistant",
        parts=[
            types.ToolCall(
                id="get_capital_0",
                name="get_capital",
                arguments={"city": "Paris"},
            )
        ],
    ),
    types.InputMessage(
        role="user",
        parts=[
            types.ToolCallResponse(
                id="get_capital_0", response={"capital": "Paris"}
            )
        ],
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

FAKE_TOOL_DEFINITIONS: list[types.ToolDefinition] = [
        types.FunctionToolDefinition(
                name="test_tool",
                description="does something",
                parameters=None,
                type="function",
        ),
]


class ThreadSafeMagicMock(MagicMock):
    def __init__(self, *args, **kwargs) -> None:
        self.__dict__["_lock"] = threading.Lock()
        super().__init__(*args, **kwargs)

    def _increment_mock_call(self, /, *args, **kwargs):
        with self.__dict__["_lock"]:
            super()._increment_mock_call(*args, **kwargs)


class TestUploadCompletionHook(TestCase):
    def setUp(self):
        self._fsspec_patcher = patch(
            "opentelemetry.util.genai._upload.completion_hook.fsspec"
        )
        mock_fsspec = self._fsspec_patcher.start()
        self.mock_fs = ThreadSafeMagicMock()
        mock_fsspec.url_to_fs.return_value = self.mock_fs, ""
        self.mock_fs.exists.return_value = False

        self.hook = UploadCompletionHook(
            base_path=BASE_PATH, max_queue_size=MAXSIZE, lru_cache_max_size=5
        )

    def tearDown(self) -> None:
        self.hook.shutdown()
        self._fsspec_patcher.stop()

    @contextmanager
    def block_upload(self):
        unblock_upload = threading.Event()

        def blocked_upload(*args: Any, **kwargs: Any):
            unblock_upload.wait()
            return MagicMock()

        try:
            self.mock_fs.open.side_effect = blocked_upload
            yield
        finally:
            unblock_upload.set()

    def test_shutdown_no_items(self):
        self.hook.shutdown()

    @skipIf(
        python_implementation().lower() == "pypy",
        "fails randomly on pypy: https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3812",
    )
    def test_upload_then_shutdown(self):
        self.hook.on_completion(
            inputs=FAKE_INPUTS,
            outputs=FAKE_OUTPUTS,
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
            tool_definitions=FAKE_TOOL_DEFINITIONS,
        )
        # all items should be consumed
        self.hook.shutdown()
        # TODO: https://github.com/open-telemetry/opentelemetry-python-contrib/issues/3812 fix flaky test that requires sleep.
        time.sleep(0.5)
        self.assertEqual(
            self.mock_fs.open.call_count,
            4,
            "should have uploaded 4 files",
        )

    def test_lru_cache_works(self):
        record = LogRecord()
        self.hook.on_completion(
            inputs=[],
            outputs=[],
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
            tool_definitions=[],
            log_record=record,
        )
        # Wait a bit for file upload to finish..
        time.sleep(0.5)
        self.assertIsNotNone(record.attributes)
        self.assertTrue(
            self.hook._file_exists(
                record.attributes["gen_ai.system_instructions_ref"]
            )
        )
        # LRU cache has a size of 5. So only AFTER 5 uploads should the original file be removed from the cache.
        for iteration in range(5):
            self.assertTrue(
                record.attributes["gen_ai.system_instructions_ref"]
                in self.hook.lru_dict
            )
            self.hook.on_completion(
                inputs=[],
                outputs=[],
                system_instruction=[types.Text(content=str(iteration))],
                tool_definitions=[],
            )
        self.hook.shutdown()
        self.assertFalse(
            record.attributes["gen_ai.system_instructions_ref"]
            in self.hook.lru_dict
        )

    def test_upload_when_inputs_outputs_empty(self):
        record = LogRecord()
        self.hook.on_completion(
            inputs=[],
            outputs=[],
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
            tool_definitions=[],
            log_record=record,
        )
        # all items should be consumed
        self.hook.shutdown()

        self.assertEqual(
            self.mock_fs.open.call_count,
            1,
            "should have uploaded 1 file",
        )
        self.assertIsNotNone(record.attributes)
        for ref_key in [
            "gen_ai.input.messages_ref",
            "gen_ai.output.messages_ref",
            "gen_ai.system_instructions_ref",
        ]:
            if ref_key == "gen_ai.system_instructions_ref":
                self.assertIn(ref_key, record.attributes)
            else:
                self.assertNotIn(ref_key, record.attributes)

    def test_upload_blocked(self):
        with self.block_upload():
            # fill the queue
            for _ in range(MAXSIZE):
                self.hook.on_completion(
                    inputs=FAKE_INPUTS,
                    outputs=FAKE_OUTPUTS,
                    system_instruction=FAKE_SYSTEM_INSTRUCTION,
                    tool_definitions=FAKE_TOOL_DEFINITIONS,
                )

            self.assertLessEqual(
                self.mock_fs.open.call_count,
                MAXSIZE,
                f"uploader should only be called {MAXSIZE=} times",
            )

            with self.assertLogs(level=logging.WARNING) as logs:
                self.hook.on_completion(
                    inputs=FAKE_INPUTS,
                    outputs=FAKE_OUTPUTS,
                    system_instruction=FAKE_SYSTEM_INSTRUCTION,
                    tool_definitions=FAKE_TOOL_DEFINITIONS,
                )

            self.assertIn(
                "upload queue is full, dropping upload", logs.output[0]
            )

    def test_shutdown_timeout(self):
        with self.block_upload():
            self.hook.on_completion(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
                tool_definitions=FAKE_TOOL_DEFINITIONS,
            )

            # shutdown should timeout and return even though there are still items in the queue
            self.hook.shutdown(timeout_sec=0.01)

    def test_failed_upload_logs(self):
        self.mock_fs.open.side_effect = RuntimeError("failed to upload")

        with self.assertLogs(level=logging.ERROR) as logs:
            self.hook.on_completion(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
                tool_definitions=FAKE_TOOL_DEFINITIONS,
            )
            self.hook.shutdown()

        self.assertIn("uploader failed", logs.output[0])

    def test_invalid_upload_format(self):
        with self.assertRaisesRegex(ValueError, "Invalid upload_format"):
            UploadCompletionHook(base_path=BASE_PATH, upload_format="invalid")

    def test_upload_format_sets_content_type(self):
        for upload_format, expect_content_type in (
            ("json", "application/json"),
            ("jsonl", "application/jsonl"),
        ):
            hook = UploadCompletionHook(
                base_path=BASE_PATH, upload_format=upload_format
            )
            self.addCleanup(hook.shutdown)

            hook.on_completion(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
                tool_definitions=FAKE_TOOL_DEFINITIONS,
            )
            hook.shutdown()

            self.mock_fs.open.assert_called_with(
                ANY, "w", content_type=expect_content_type
            )

    def test_upload_after_shutdown_logs(self):
        self.hook.shutdown()
        with self.assertLogs(level=logging.INFO) as logs:
            self.hook.on_completion(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
                tool_definitions=FAKE_TOOL_DEFINITIONS,
            )
        self.assertEqual(len(logs.output), 4)
        self.assertIn(
            "attempting to upload file after UploadCompletionHook.shutdown() was already called",
            logs.output[0],
        )

    def test_threadpool_max_workers(self):
        for max_queue_size, expect_threadpool_workers in ((10, 10), (100, 64)):
            with patch(
                "opentelemetry.util.genai._upload.completion_hook.ThreadPoolExecutor"
            ) as mock:
                hook = UploadCompletionHook(
                    base_path=BASE_PATH, max_queue_size=max_queue_size
                )
                self.addCleanup(hook.shutdown)
                mock.assert_called_once_with(
                    max_workers=expect_threadpool_workers
                )


class TestUploadCompletionHookIntegration(TestBase):
    def setUp(self):
        super().setUp()
        self.hook = UploadCompletionHook(base_path=BASE_PATH)

    def create_hook(self) -> UploadCompletionHook:
        self.hook = UploadCompletionHook(base_path=BASE_PATH)
        return self.hook

    def tearDown(self):
        super().tearDown()
        self.hook.shutdown()

    def assert_fsspec_equal(self, path: str, value: str) -> None:
        with fsspec.open(path, "r") as file:
            self.assertEqual(file.read(), value)

    def test_system_insruction_is_hashed_to_avoid_reupload(self):
        expected_hash = (
            "7e35acac4feca03ab47929d4cc6cfef1df2190ae1ee1752196a05ffc2a6cb360"
        )
        # Create the file before upload..
        expected_file_name = (
            f"memory://{expected_hash}_system_instruction.json"
        )
        with fsspec.open(expected_file_name, "wb") as file:
            file.write(b"asg")
        # FIle should exist.
        self.assertTrue(self.hook._file_exists(expected_file_name))
        system_instructions = [
            types.Text(content="You are a helpful assistant."),
            types.Text(content="You will do your best."),
        ]
        record = LogRecord()
        self.hook.on_completion(
            inputs=[],
            outputs=[],
            system_instruction=system_instructions,
            tool_definitions=[],
            log_record=record,
        )
        self.hook.shutdown()
        self.assertIsNotNone(record.attributes)

        self.assertEqual(
            record.attributes["gen_ai.system_instructions_ref"],
            expected_file_name,
        )
        # Content should not have been overwritten.
        self.assert_fsspec_equal(expected_file_name, "asg")

    def test_tool_definitions_is_hashed_to_avoid_reupload(self):
        expected_hash = (
            "1f559d0102f8c440a667fd5ed587beeed488ec9f3ce0828d39c424bed6546cf5"
        )
        # Create the file before upload..
        expected_file_name = f"memory://{expected_hash}_tool.definitions.json"
        with fsspec.open(expected_file_name, "wb") as file:
            file.write(b"asg")
        # FIle should exist.
        self.assertTrue(self.hook._file_exists(expected_file_name))
        tool_definitions = [
                types.FunctionToolDefinition(
                        name="some_tool",
                        description="does something",
                        parameters=None,
                        type="function",
                ),
        ]
        record = LogRecord()
        self.hook.on_completion(
            inputs=[],
            outputs=[],
            system_instruction=[],
            tool_definitions=tool_definitions,
            log_record=record,
        )
        self.hook.shutdown()
        self.assertIsNotNone(record.attributes)

        self.assertEqual(
            record.attributes["gen_ai.tool.definitions_ref"],
            expected_file_name,
        )
        # Content should not have been overwritten.
        self.assert_fsspec_equal(expected_file_name, "asg")

    def test_upload_completions(self):
        tracer = self.tracer_provider.get_tracer(__name__)
        log_record = LogRecord()

        with tracer.start_as_current_span("chat mymodel") as span:
            self.hook.on_completion(
                inputs=FAKE_INPUTS,
                outputs=FAKE_OUTPUTS,
                system_instruction=FAKE_SYSTEM_INSTRUCTION,
                tool_definitions=FAKE_TOOL_DEFINITIONS,
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
                "gen_ai.tool.definitions_ref",
            ]:
                self.assertIn(ref_key, attributes)

        self.assert_fsspec_equal(
            span.attributes["gen_ai.input.messages_ref"],
            '[{"role":"user","parts":[{"content":"What is the capital of France?","type":"text"}]},{"role":"assistant","parts":[{"arguments":{"city":"Paris"},"name":"get_capital","id":"get_capital_0","type":"tool_call"}]},{"role":"user","parts":[{"response":{"capital":"Paris"},"id":"get_capital_0","type":"tool_call_response"}]}]\n',
        )
        self.assert_fsspec_equal(
            span.attributes["gen_ai.output.messages_ref"],
            '[{"role":"assistant","parts":[{"content":"Paris","type":"text"}],"finish_reason":"stop"}]\n',
        )
        self.assert_fsspec_equal(
            span.attributes["gen_ai.system_instructions_ref"],
            '[{"content":"You are a helpful assistant.","type":"text"}]\n',
        )
        self.assert_fsspec_equal(
            span.attributes["gen_ai.tool.definitions_ref"],
            '[{"name":"test_tool","description":"does something","parameters":null,"type":"function"}]\n',
        )

    def test_stamps_empty_log(self):
        log_record = LogRecord()
        self.hook.on_completion(
            inputs=FAKE_INPUTS,
            outputs=FAKE_OUTPUTS,
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
            tool_definitions=FAKE_TOOL_DEFINITIONS,
            log_record=log_record,
        )

        # stamp on both body and attributes
        self.assertIn("gen_ai.input.messages_ref", log_record.attributes)
        self.assertIn("gen_ai.output.messages_ref", log_record.attributes)
        self.assertIn("gen_ai.system_instructions_ref", log_record.attributes)
        self.assertIn("gen_ai.tool.definitions_ref", log_record.attributes)

    def test_upload_bytes(self) -> None:
        log_record = LogRecord()
        self.hook.on_completion(
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
            tool_definitions=FAKE_TOOL_DEFINITIONS,
            log_record=log_record,
        )
        self.hook.shutdown()

        self.assert_fsspec_equal(
            log_record.attributes["gen_ai.input.messages_ref"],
            '[{"role":"user","parts":[{"content":"What is the capital of France?","type":"text"},{"type":"generic_bytes","bytes":"aGVsbG8="}]}]\n',
        )

    def test_upload_json(self) -> None:
        hook = UploadCompletionHook(base_path=BASE_PATH, upload_format="json")
        self.addCleanup(hook.shutdown)
        log_record = LogRecord()

        hook.on_completion(
            inputs=FAKE_INPUTS,
            outputs=FAKE_OUTPUTS,
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
            tool_definitions=FAKE_TOOL_DEFINITIONS,
            log_record=log_record,
        )
        hook.shutdown()

        ref_uri: str = log_record.attributes["gen_ai.input.messages_ref"]
        self.assertTrue(
            ref_uri.endswith(".json"), f"{ref_uri=} does not end with .json"
        )

        self.assert_fsspec_equal(
            ref_uri,
            '[{"role":"user","parts":[{"content":"What is the capital of France?","type":"text"}]},{"role":"assistant","parts":[{"arguments":{"city":"Paris"},"name":"get_capital","id":"get_capital_0","type":"tool_call"}]},{"role":"user","parts":[{"response":{"capital":"Paris"},"id":"get_capital_0","type":"tool_call_response"}]}]\n',
        )

    def test_upload_jsonlines(self) -> None:
        hook = UploadCompletionHook(base_path=BASE_PATH, upload_format="jsonl")
        self.addCleanup(hook.shutdown)
        log_record = LogRecord()

        hook.on_completion(
            inputs=FAKE_INPUTS,
            outputs=FAKE_OUTPUTS,
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
            tool_definitions=FAKE_TOOL_DEFINITIONS,
            log_record=log_record,
        )
        hook.shutdown()

        ref_uri: str = log_record.attributes["gen_ai.input.messages_ref"]
        self.assertTrue(
            ref_uri.endswith(".jsonl"), f"{ref_uri=} does not end with .jsonl"
        )

        self.assert_fsspec_equal(
            ref_uri,
            """\
{"role":"user","parts":[{"content":"What is the capital of France?","type":"text"}],"index":0}
{"role":"assistant","parts":[{"arguments":{"city":"Paris"},"name":"get_capital","id":"get_capital_0","type":"tool_call"}],"index":1}
{"role":"user","parts":[{"response":{"capital":"Paris"},"id":"get_capital_0","type":"tool_call_response"}],"index":2}
""",
        )

    def test_upload_chained_filesystem_ref(self) -> None:
        """Using a chained filesystem like simplecache should refer to the final remote destination"""
        hook = UploadCompletionHook(
            base_path="simplecache::memory",
            upload_format="jsonl",
        )
        self.addCleanup(hook.shutdown)
        log_record = LogRecord()

        hook.on_completion(
            inputs=FAKE_INPUTS,
            outputs=FAKE_OUTPUTS,
            system_instruction=FAKE_SYSTEM_INSTRUCTION,
            tool_definitions=FAKE_TOOL_DEFINITIONS,
            log_record=log_record,
        )
        hook.shutdown()

        ref_uri: str = log_record.attributes["gen_ai.input.messages_ref"]
        self.assertTrue(
            ref_uri.startswith("memory://"),
            f"{ref_uri=} does not start with final destination uri memory://",
        )
