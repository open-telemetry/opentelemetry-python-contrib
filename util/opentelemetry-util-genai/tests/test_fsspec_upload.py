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
from unittest import TestCase
from unittest.mock import MagicMock, patch

from opentelemetry.util.genai._fsspec_upload import (
    Completion,
    FsspecCompletionExporter,
    FsspecUploadHook,
)
from opentelemetry.util.genai.upload_hook import (
    _NoOpUploadHook,
    load_upload_hook,
)


@patch.dict(
    "os.environ",
    {"OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK": "fsspec"},
    clear=True,
)
class TestFsspecEntryPoint(TestCase):
    def test_fsspec_entry_point(self):
        self.assertIsInstance(load_upload_hook(), FsspecUploadHook)

    def test_fsspec_entry_point_no_fsspec(self):
        """Tests that the a no-op uploader is used when fsspec is not installed"""

        from opentelemetry.util.genai import _fsspec_upload

        # Simulate fsspec imports failing
        with patch.dict(sys.modules, {"fsspec": None}):
            importlib.reload(_fsspec_upload)
            self.assertIsInstance(load_upload_hook(), _NoOpUploadHook)


MAXSIZE = 5
SHUTDOWN_TIMEOUT = 0.5


class TestFsspecUploadHook(TestCase):
    def setUp(self):
        self.mock_exporter = MagicMock(spec=FsspecCompletionExporter)
        self.hook = FsspecUploadHook(self.mock_exporter, maxsize=MAXSIZE)

    def tearDown(self) -> None:
        self.hook.shutdown(timeout_sec=SHUTDOWN_TIMEOUT)

    def test_fsspec_upload_hook_shutdown_no_items(self):
        self.hook.shutdown(timeout_sec=SHUTDOWN_TIMEOUT)

    def test_fsspec_upload_hook_upload_then_shutdown(self):
        for _ in range(10):
            self.hook.upload(
                inputs=[],
                outputs=[],
                system_instruction=[],
            )
        # all items should be consumed
        self.hook.shutdown(timeout_sec=SHUTDOWN_TIMEOUT)

    def test_fsspec_upload_hook_upload_blocked(self):
        unblock_export = threading.Event()

        def blocked_export(completion: Completion) -> None:
            unblock_export.wait()

        self.mock_exporter.export = MagicMock(wraps=blocked_export)

        # fill the queue
        for _ in range(10):
            self.hook.upload(
                inputs=[],
                outputs=[],
                system_instruction=[],
            )

        self.assertLessEqual(self.mock_exporter.export.call_count, MAXSIZE)

        # attempt to enqueue when full should wawrn
        with self.assertLogs(level=logging.WARNING) as logs:
            self.hook.upload(
                inputs=[],
                outputs=[],
                system_instruction=[],
            )

        self.assertEqual(len(logs.output), 1)
        unblock_export.set()

        # all items should be consumed
        self.hook.shutdown(timeout_sec=SHUTDOWN_TIMEOUT)
