import os
import unittest
from unittest.mock import patch

from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATORS,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


class TestEvaluationPipeline(unittest.TestCase):
    def _build_invocation(self, content: str) -> LLMInvocation:
        inv = LLMInvocation(request_model="m", provider="p")
        inv.input_messages.append(
            InputMessage(role="user", parts=[Text(content="hello")])
        )
        inv.output_messages.append(
            OutputMessage(
                role="assistant",
                parts=[Text(content=content)],
                finish_reason="stop",
            )
        )
        return inv

    def _fresh_handler(self):
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        return get_telemetry_handler()

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "length",
        },
        clear=True,
    )
    def test_stop_llm_triggers_evaluation_immediately(self):
        handler = self._fresh_handler()
        inv = self._build_invocation("Hello world")
        recorded = {"metrics": [], "events": []}
        original_record = handler._evaluation_histogram.record  # type: ignore[attr-defined]
        original_emit = handler._event_logger.emit  # type: ignore[attr-defined]

        def fake_record(value, attributes=None):
            recorded["metrics"].append((value, dict(attributes or {})))

        def fake_emit(event):
            recorded["events"].append(event)

        handler._evaluation_histogram.record = fake_record  # type: ignore
        handler._event_logger.emit = fake_emit  # type: ignore

        handler.start_llm(inv)
        handler.stop_llm(inv)

        self.assertTrue(recorded["metrics"], "Expected evaluation metric")
        self.assertTrue(recorded["events"], "Expected evaluation event")
        self.assertTrue(
            inv.attributes.get("gen_ai.evaluation.executed"),
            "Attribute should mark evaluation execution",
        )

        handler._evaluation_histogram.record = original_record  # type: ignore
        handler._event_logger.emit = original_emit  # type: ignore

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "false",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "length",
        },
        clear=True,
    )
    def test_disabled_evaluation_produces_no_signals(self):
        handler = self._fresh_handler()
        inv = self._build_invocation("Hello world")
        recorded = {"metrics": [], "events": []}
        original_record = handler._evaluation_histogram.record  # type: ignore[attr-defined]
        original_emit = handler._event_logger.emit  # type: ignore[attr-defined]

        def fake_record(value, attributes=None):
            recorded["metrics"].append(value)

        def fake_emit(event):
            recorded["events"].append(event)

        handler._evaluation_histogram.record = fake_record  # type: ignore
        handler._event_logger.emit = fake_emit  # type: ignore

        handler.start_llm(inv)
        handler.stop_llm(inv)

        self.assertFalse(recorded["metrics"])
        self.assertFalse(recorded["events"])
        self.assertNotIn("gen_ai.evaluation.executed", inv.attributes)

        handler._evaluation_histogram.record = original_record  # type: ignore
        handler._event_logger.emit = original_emit  # type: ignore


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
