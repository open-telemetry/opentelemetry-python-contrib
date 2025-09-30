import os
import unittest
from unittest.mock import patch

from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATORS,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


class TestAsyncEvaluation(unittest.TestCase):
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

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "length",
            # Large interval to prevent background worker from racing in test
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL: "30",
        },
        clear=True,
    )
    def test_sampling_and_manual_process(self):
        # Fresh handler
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        handler = get_telemetry_handler()
        inv = self._build_invocation("Hello async world!")
        recorded = {"metrics": [], "events": []}
        # Patch metric + events
        orig_record = handler._evaluation_histogram.record  # type: ignore[attr-defined]
        orig_emit = handler._event_logger.emit  # type: ignore[attr-defined]

        def fake_record(v, attributes=None):
            recorded["metrics"].append((v, dict(attributes or {})))

        def fake_emit(evt):
            recorded["events"].append(evt)

        handler._evaluation_histogram.record = fake_record  # type: ignore
        handler._event_logger.emit = fake_emit  # type: ignore

        handler.start_llm(inv)
        handler.stop_llm(inv)  # enqueue via offer
        # Manually trigger processing
        handler._evaluation_manager.process_once()  # type: ignore[attr-defined]
        self.assertTrue(
            recorded["metrics"], "Expected at least one metric from async eval"
        )
        self.assertTrue(
            recorded["events"], "Expected an evaluation event from async eval"
        )
        # Restore
        handler._evaluation_histogram.record = orig_record  # type: ignore
        handler._event_logger.emit = orig_emit  # type: ignore

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "length",
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_INTERVAL: "30",
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_MAX_PER_MINUTE: "1",
        },
        clear=True,
    )
    def test_rate_limit_per_minute(self):
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        handler = get_telemetry_handler()
        recorded = {"metrics": []}
        orig_record = handler._evaluation_histogram.record  # type: ignore[attr-defined]

        def fake_record(v, attributes=None):
            recorded["metrics"].append(v)

        handler._evaluation_histogram.record = fake_record  # type: ignore

        inv1 = self._build_invocation("sample one")
        inv2 = self._build_invocation("sample two longer text")
        handler.start_llm(inv1)
        handler.stop_llm(inv1)
        handler.start_llm(inv2)
        handler.stop_llm(inv2)
        handler._evaluation_manager.process_once()  # type: ignore[attr-defined]
        # Only one should have been evaluated due to rate limit
        self.assertEqual(len(recorded["metrics"]), 1)
        handler._evaluation_histogram.record = orig_record  # type: ignore


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
