import importlib
import os
import unittest
from typing import Sequence
from unittest.mock import patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATORS,
)
from opentelemetry.util.genai.evaluators import registry as evaluator_registry
from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util.genai.evaluators.registry import (
    clear_registry,
    register_evaluator,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    EvaluationResult,
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)


def _reload_builtin_evaluators() -> None:
    from opentelemetry.util.genai.evaluators import builtins as builtin_module

    importlib.reload(builtin_module)


class TestHandlerEvaluationTelemetry(unittest.TestCase):
    def setUp(self):
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        clear_registry()
        _reload_builtin_evaluators()
        self.invocation = LLMInvocation(
            request_model="model-y", provider="prov"
        )
        self.invocation.input_messages.append(
            InputMessage(
                role="user", parts=[Text(content="Tell me something short")]
            )
        )
        self.invocation.output_messages.append(
            OutputMessage(
                role="assistant",
                parts=[Text(content="Hello world!")],
                finish_reason="stop",
            )
        )

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "length",
        },
        clear=True,
    )
    def test_length_evaluator_emits_event_and_metric(self):
        handler = get_telemetry_handler()
        recorded = {"metrics": [], "events": []}
        original_hist = handler._evaluation_histogram  # pylint: disable=protected-access
        original_emit = handler._event_logger.emit  # pylint: disable=protected-access

        def fake_record(value, attributes=None):
            recorded["metrics"].append((value, dict(attributes or {})))

        def fake_emit(event):
            recorded["events"].append(event)

        handler._evaluation_histogram.record = fake_record  # type: ignore
        handler._event_logger.emit = fake_emit  # type: ignore
        try:
            results = handler.evaluate_llm(self.invocation)
            self.assertEqual(len(results), 1)
            res = results[0]
            self.assertEqual(res.metric_name, "length")
            self.assertIsNotNone(res.score)
            self.assertEqual(len(recorded["metrics"]), 1)
            metric_val, metric_attrs = recorded["metrics"][0]
            self.assertAlmostEqual(metric_val, res.score)
            self.assertEqual(
                metric_attrs.get("gen_ai.evaluation.name"), "length"
            )
            self.assertEqual(len(recorded["events"]), 1)
            evt = recorded["events"][0]
            self.assertEqual(evt.name, "gen_ai.evaluations")
            body_item = evt.body["evaluations"][0]
            self.assertEqual(body_item["gen_ai.evaluation.name"], "length")
        finally:
            handler._evaluation_histogram = original_hist  # type: ignore
            handler._event_logger.emit = original_emit  # type: ignore

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "deepeval",
        },
        clear=True,
    )
    def test_deepeval_missing_dependency_error_event(self):
        handler = get_telemetry_handler()
        recorded = {"events": []}
        original_emit = handler._event_logger.emit  # pylint: disable=protected-access

        def fake_emit(event):
            recorded["events"].append(event)

        handler._event_logger.emit = fake_emit  # type: ignore
        try:
            results = handler.evaluate_llm(self.invocation)
            self.assertEqual(len(results), 1)
            res = results[0]
            self.assertEqual(res.metric_name, "deepeval")
            self.assertIsNotNone(res.error)
            self.assertEqual(len(recorded["events"]), 1)
            body_item = recorded["events"][0].body["evaluations"][0]
            self.assertEqual(body_item["gen_ai.evaluation.name"], "deepeval")
            self.assertIn("error.type", body_item)
        finally:
            handler._event_logger.emit = original_emit  # type: ignore


class _SpanModeDummyEvaluator(Evaluator):
    def __init__(
        self,
        name: str,
        score: float,
        metrics: Sequence[str] | None = None,
    ) -> None:
        self._name = name
        self._score = score
        super().__init__(metrics)

    def default_metrics(self) -> Sequence[str]:  # pragma: no cover - trivial
        return (self._name,)

    def evaluate_llm(
        self, invocation: LLMInvocation
    ) -> Sequence[EvaluationResult]:  # pragma: no cover - trivial
        metric = self.metrics[0] if self.metrics else self._name
        return [
            EvaluationResult(metric_name=metric, score=self._score, label="ok")
        ]


class TestHandlerEvaluationSpanModes(unittest.TestCase):
    def setUp(self):
        self.span_exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.span_exporter))
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        clear_registry()
        _reload_builtin_evaluators()
        self.provider = provider
        self.invocation = LLMInvocation(request_model="m", provider="prov")
        self.invocation.input_messages.append(
            InputMessage(role="user", parts=[Text(content="Hi")])
        )
        self.invocation.output_messages.append(
            OutputMessage(
                role="assistant",
                parts=[Text(content="Hello there")],
                finish_reason="stop",
            )
        )

    def _run(self, eval_list: str):
        if "dummy" in eval_list:
            register_evaluator(
                "dummy",
                lambda metrics=None: _SpanModeDummyEvaluator(
                    "dummy", 0.9, metrics=metrics
                ),
            )
        if "dummy2" in eval_list:
            register_evaluator(
                "dummy2",
                lambda metrics=None: _SpanModeDummyEvaluator(
                    "dummy2", 0.7, metrics=metrics
                ),
            )
        handler = get_telemetry_handler(tracer_provider=self.provider)
        handler.start_llm(self.invocation)
        handler.stop_llm(self.invocation)
        return self.span_exporter.get_finished_spans()

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "length",
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE: "aggregated",
        },
        clear=True,
    )
    def test_aggregated_span_mode(self):
        spans = self._run("length")
        names = [s.name for s in spans]
        self.assertTrue(any(n.startswith("chat") for n in names))
        self.assertIn("evaluation", names)
        self.assertEqual(len([n for n in names if n == "evaluation"]), 1)

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "length,dummy,dummy2",
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_SPAN_MODE: "per_metric",
        },
        clear=True,
    )
    def test_per_metric_span_mode(self):
        spans = self._run("length,dummy,dummy2")
        names = [s.name for s in spans]
        self.assertTrue(any(n.startswith("chat") for n in names))
        metric_spans = [n for n in names if n.startswith("evaluation.")]
        self.assertIn("evaluation.length", metric_spans)
        self.assertIn("evaluation.dummy", metric_spans)
        self.assertIn("evaluation.dummy2", metric_spans)


def tearDownModule():  # pragma: no cover - test hygiene
    if hasattr(get_telemetry_handler, "_default_handler"):
        delattr(get_telemetry_handler, "_default_handler")
    evaluator_registry.clear_registry()
