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

import logging
from dataclasses import dataclass
from typing import Any, Callable
from unittest import TestCase
from unittest.mock import Mock, patch

from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK,
)
from opentelemetry.util.genai.upload_hook import (
    UploadHook,
    _NoOpUploadHook,
    load_upload_hook,
)


class FakeUploadHook(UploadHook):
    def upload(self, **kwargs: Any):
        pass


class InvalidUploadHook:
    pass


@dataclass
class FakeEntryPoint:
    name: str
    load: Callable[[], type[UploadHook]]


class TestUploadHook(TestCase):
    @patch.dict("os.environ", {})
    def test_load_upload_hook_noop(self):
        self.assertIsInstance(load_upload_hook(), _NoOpUploadHook)

    @patch(
        "opentelemetry.util.genai.upload_hook.entry_points",
    )
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK: "my-hook"}
    )
    def test_load_upload_hook_custom(self, mock_entry_points: Mock):
        mock_entry_points.return_value = [
            FakeEntryPoint("my-hook", lambda: FakeUploadHook)
        ]

        self.assertIsInstance(load_upload_hook(), FakeUploadHook)

    @patch("opentelemetry.util.genai.upload_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK: "my-hook"}
    )
    def test_load_upload_hook_invalid(self, mock_entry_points: Mock):
        mock_entry_points.return_value = [
            FakeEntryPoint("my-hook", lambda: InvalidUploadHook)
        ]

        with self.assertLogs(level=logging.DEBUG) as logs:
            self.assertIsInstance(load_upload_hook(), _NoOpUploadHook)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("is not a valid UploadHook. Using noop", logs.output[0])

    @patch("opentelemetry.util.genai.upload_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK: "my-hook"}
    )
    def test_load_upload_hook_error(self, mock_entry_points: Mock):
        def load():
            raise RuntimeError("error")

        mock_entry_points.return_value = [FakeEntryPoint("my-hook", load)]

        self.assertIsInstance(load_upload_hook(), _NoOpUploadHook)

    @patch("opentelemetry.util.genai.upload_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK: "my-hook"}
    )
    def test_load_upload_hook_not_found(self, mock_entry_points: Mock):
        mock_entry_points.return_value = [
            FakeEntryPoint("other-hook", lambda: FakeUploadHook)
        ]

        self.assertIsInstance(load_upload_hook(), _NoOpUploadHook)
