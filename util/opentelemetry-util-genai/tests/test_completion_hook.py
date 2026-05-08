# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
from dataclasses import dataclass
from typing import Any, Callable
from unittest import TestCase
from unittest.mock import Mock, patch

from opentelemetry.util.genai.completion_hook import (
    CompletionHook,
    _NoOpCompletionHook,
    _SafeCompletionHook,
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

        hook = load_completion_hook()
        self.assertIsInstance(hook, _SafeCompletionHook)
        self.assertIsInstance(hook._wrapped, FakeCompletionHook)

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


class TestSafeCompletionHook(TestCase):
    def test_passes_arguments_to_wrapped_hook(self):
        wrapped = Mock(spec=CompletionHook)
        safe = _SafeCompletionHook(wrapped)

        kwargs = {
            "inputs": [],
            "outputs": [],
            "system_instruction": [],
            "span": None,
            "log_record": None,
        }
        safe.on_completion(**kwargs)

        self.assertEqual(wrapped.on_completion.call_count, 1)
        self.assertEqual(wrapped.on_completion.call_args.kwargs, kwargs)

    def test_swallows_exception_from_wrapped_hook(self):
        class RaisingCompletionHook(CompletionHook):
            def on_completion(self, **kwargs: Any) -> None:
                raise RuntimeError("boom")

        safe = _SafeCompletionHook(RaisingCompletionHook())

        with self.assertLogs(
            "opentelemetry.util.genai.completion_hook", level=logging.WARNING
        ) as logs:
            safe.on_completion(
                inputs=[],
                outputs=[],
                system_instruction=[],
            )

        self.assertEqual(len(logs.records), 1)
        self.assertEqual(logs.records[0].levelno, logging.WARNING)
        self.assertIn("raised an exception", logs.records[0].getMessage())
        self.assertIsInstance(logs.records[0].exc_info[1], RuntimeError)

    def test_does_not_swallow_keyboard_interrupt(self):
        class InterruptingCompletionHook(CompletionHook):
            def on_completion(self, **kwargs: Any) -> None:
                raise KeyboardInterrupt

        safe = _SafeCompletionHook(InterruptingCompletionHook())

        with self.assertRaises(KeyboardInterrupt):
            safe.on_completion(
                inputs=[],
                outputs=[],
                system_instruction=[],
            )
