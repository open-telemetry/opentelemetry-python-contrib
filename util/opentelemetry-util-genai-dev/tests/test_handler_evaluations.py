import os
import unittest
from unittest.mock import patch

from opentelemetry.util.genai.callbacks import CompletionCallback
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


class _RecordingCallback(CompletionCallback):
    def __init__(self) -> None:
        self.invocations = 0

    def on_completion(self, invocation) -> None:
        self.invocations += 1


class TestHandlerCompletionCallbacks(unittest.TestCase):
    def setUp(self) -> None:
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")

    def _build_invocation(self) -> LLMInvocation:
        invocation = LLMInvocation(request_model="cb-model")
        invocation.input_messages.append(
            InputMessage(role="user", parts=[Text(content="hi")])
        )
        invocation.output_messages.append(
            OutputMessage(
                role="assistant",
                parts=[Text(content="hello")],
                finish_reason="stop",
            )
        )
        return invocation

    def test_manual_callback_invoked(self) -> None:
        handler = get_telemetry_handler()
        callback = _RecordingCallback()
        handler.register_completion_callback(callback)
        invocation = self._build_invocation()
        handler.start_llm(invocation)
        handler.stop_llm(invocation)
        self.assertEqual(callback.invocations, 1)

    @patch.dict(
        os.environ,
        {OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS: "length"},
        clear=True,
    )
    def test_default_manager_registered_when_env_set(self) -> None:
        handler = get_telemetry_handler()
        manager = getattr(handler, "_evaluation_manager", None)
        self.assertIsNotNone(manager)
        if manager is not None:
            manager.shutdown()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
