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

from opentelemetry.util.genai.completion_hook import (
    CompletionHook,
    _NoOpCompletionHook,
    load_completion_hook,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK,
)


class FakeCompletionHook(CompletionHook):
    def on_completion(self, **kwargs: Any):
        pass


class InvalidCompletionHook:
    pass


@dataclass
class FakeEntryPoint:
    name: str
    load: Callable[[], type[CompletionHook]]


class TestCompletionHook(TestCase):
    @patch.dict("os.environ", {})
    def test_load_completion_hook_noop(self):
        self.assertIsInstance(load_completion_hook(), _NoOpCompletionHook)

    @patch(
        "opentelemetry.util.genai.completion_hook.entry_points",
    )
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK: "my-hook"}
    )
    def test_load_completion_hook_custom(self, mock_entry_points: Mock):
        mock_entry_points.return_value = [
            FakeEntryPoint("my-hook", lambda: FakeCompletionHook)
        ]

        self.assertIsInstance(load_completion_hook(), FakeCompletionHook)

    @patch("opentelemetry.util.genai.completion_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK: "my-hook"}
    )
    def test_load_completion_hook_invalid(self, mock_entry_points: Mock):
        mock_entry_points.return_value = [
            FakeEntryPoint("my-hook", lambda: InvalidCompletionHook)
        ]

        with self.assertLogs(level=logging.DEBUG) as logs:
            self.assertIsInstance(load_completion_hook(), _NoOpCompletionHook)
        self.assertEqual(len(logs.output), 1)
        self.assertIn(
            "is not a valid CompletionHook. Using noop", logs.output[0]
        )

    @patch("opentelemetry.util.genai.completion_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK: "my-hook"}
    )
    def test_load_completion_hook_error(self, mock_entry_points: Mock):
        def load():
            raise RuntimeError("error")

        mock_entry_points.return_value = [FakeEntryPoint("my-hook", load)]

        self.assertIsInstance(load_completion_hook(), _NoOpCompletionHook)

    @patch("opentelemetry.util.genai.completion_hook.entry_points")
    @patch.dict(
        "os.environ", {OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK: "my-hook"}
    )
    def test_load_completion_hook_not_found(self, mock_entry_points: Mock):
        mock_entry_points.return_value = [
            FakeEntryPoint("other-hook", lambda: FakeCompletionHook)
        ]

        self.assertIsInstance(load_completion_hook(), _NoOpCompletionHook)
