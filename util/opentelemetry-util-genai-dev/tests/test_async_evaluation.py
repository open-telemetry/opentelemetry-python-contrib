import os
import types
import unittest
from unittest.mock import patch

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


class TestAsyncEvaluation(unittest.TestCase):
    def setUp(self) -> None:
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")

    def _build_invocation(self) -> LLMInvocation:
        invocation = LLMInvocation(request_model="async-model")
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

    @patch.dict(
        os.environ,
        {OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS: "length"},
        clear=True,
    )
    def test_async_evaluation_emits_results(self) -> None:
        handler = get_telemetry_handler()
        captured: list[str] = []

        def _capture(self, invocation, results):
            for result in results:
                captured.append(result.metric_name)

        handler.evaluation_results = types.MethodType(  # type: ignore[assignment]
            _capture,
            handler,
        )
        invocation = self._build_invocation()
        handler.start_llm(invocation)
        handler.stop_llm(invocation)
        handler.wait_for_evaluations(2.0)
        manager = getattr(handler, "_evaluation_manager", None)
        if manager is not None:
            manager.shutdown()
        self.assertIn("length", captured)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
