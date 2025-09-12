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

from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from opentelemetry.util.genai._upload_hook import (
    _no_op_upload_hook,
    load_upload_hook,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK,
)


class TestUploadHook(TestCase):
    @patch.dict("os.environ", {})
    def test_load_upload_hook_noop(self):
        self.assertIs(load_upload_hook(), _no_op_upload_hook)

    @patch("opentelemetry.util.genai._upload_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK: "my-hook"}
    )
    def test_load_upload_hook_custom(self, mock_entry_points: Mock):
        mock_hook = MagicMock()
        mock_entry_point = MagicMock()
        mock_entry_point.name = "my-hook"
        mock_entry_point.load.return_value = mock_hook
        mock_entry_points.return_value = [mock_entry_point]

        self.assertIs(load_upload_hook(), mock_hook)

    @patch("opentelemetry.util.genai._upload_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK: "my-hook"}
    )
    def test_load_upload_hook_invalid(self, mock_entry_points: Mock):
        mock_entry_point = MagicMock()
        mock_entry_point.name = "my-hook"
        mock_entry_point.load.return_value = object()
        mock_entry_points.return_value = [mock_entry_point]

        self.assertIs(load_upload_hook(), _no_op_upload_hook)

    @patch("opentelemetry.util.genai._upload_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK: "my-hook"}
    )
    def test_load_upload_hook_error(self, mock_entry_points: Mock):
        mock_entry_point = MagicMock()
        mock_entry_point.name = "my-hook"
        mock_entry_point.load.side_effect = Exception("error")
        mock_entry_points.return_value = [mock_entry_point]

        self.assertIs(load_upload_hook(), _no_op_upload_hook)

    @patch("opentelemetry.util.genai._upload_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK: "my-hook"}
    )
    def test_load_upload_hook_not_found(self, mock_entry_points: Mock):
        mock_entry_point = MagicMock()
        mock_entry_point.name = "other-hook"
        mock_entry_points.return_value = [mock_entry_point]

        self.assertIs(load_upload_hook(), _no_op_upload_hook)
