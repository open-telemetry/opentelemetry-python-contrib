# Copyright The OpenTelemetry Authors
#
# Evaluator tests: registry behavior, event & metric emission, and span modes.

import os
import sys
import unittest
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
from opentelemetry.util.genai.evaluators import (
    registry as reg,  # access for clearing
)
from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util.genai.evaluators.registry import (
    list_evaluators,
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


# ---------------- Registry & basic evaluation tests -----------------
class _DummyEvaluator(Evaluator):
    def __init__(self, name: str = "dummy", score: float = 0.42):
        self._name = name
        self._score = score

    def evaluate_invocation(
        self, invocation: LLMInvocation
    ):  # pragma: no cover - trivial
        return EvaluationResult(
            metric_name=self._name, score=self._score, label="ok"
        )


class TestEvaluatorRegistry(unittest.TestCase):
    def setUp(self):
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        reg._EVALUATORS.clear()  # pylint: disable=protected-access
        self.invocation = LLMInvocation(request_model="model-x")
        self.invocation.input_messages.append(
            InputMessage(role="user", parts=[Text(content="hi")])
        )
        self.invocation.output_messages.append(
            OutputMessage(
                role="assistant",
                parts=[Text(content="hello")],
                finish_reason="stop",
            )
        )

    @patch.dict(
        os.environ,
        {OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "false"},
        clear=True,
    )
    def test_disabled_returns_empty(self):
        handler = get_telemetry_handler()
        results = handler.evaluate_llm(
            self.invocation, ["anything"]
        )  # evaluator missing
        self.assertEqual(results, [])

    @patch.dict(
        os.environ,
        {OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true"},
        clear=True,
    )
    def test_enabled_no_evaluators_specified(self):
        handler = get_telemetry_handler()
        results = handler.evaluate_llm(self.invocation)
        self.assertEqual(results, [])

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "dummy",
        },
        clear=True,
    )
    def test_env_driven_evaluator(self):
        register_evaluator("dummy", lambda: _DummyEvaluator())
        handler = get_telemetry_handler()
        results = handler.evaluate_llm(self.invocation)
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.metric_name, "dummy")
        self.assertEqual(res.score, 0.42)
        self.assertEqual(res.label, "ok")
        self.assertIsNone(res.error)

    @patch.dict(
        os.environ,
        {OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true"},
        clear=True,
    )
    def test_unknown_evaluator_error(self):
        handler = get_telemetry_handler()
        results = handler.evaluate_llm(self.invocation, ["missing"])
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.metric_name, "missing")
        self.assertIsNotNone(res.error)
        self.assertIn("Unknown evaluator", res.error.message)

    def test_register_multiple_list(self):
        register_evaluator("dummy", lambda: _DummyEvaluator("dummy", 0.1))
        register_evaluator("dummy2", lambda: _DummyEvaluator("dummy2", 0.2))
        names = list_evaluators()
        self.assertEqual(names, ["dummy", "dummy2"])  # alphabetical sort


# ---------------- Event & metric emission tests -----------------
class TestEvaluatorTelemetry(unittest.TestCase):
    def setUp(self):
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        reg._EVALUATORS.clear()  # pylint: disable=protected-access
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

        def fake_record(value, attributes=None):
            recorded["metrics"].append((value, dict(attributes or {})))

        original_emit = handler._event_logger.emit  # pylint: disable=protected-access

        def fake_emit(event):
            recorded["events"].append(event)

        handler._evaluation_histogram.record = fake_record  # type: ignore
        handler._event_logger.emit = fake_emit  # type: ignore
        results = handler.evaluate_llm(self.invocation)
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.metric_name, "length")
        self.assertIsNotNone(res.score)
        self.assertEqual(len(recorded["metrics"]), 1)
        metric_val, metric_attrs = recorded["metrics"][0]
        self.assertAlmostEqual(metric_val, res.score)
        self.assertEqual(metric_attrs.get("gen_ai.evaluation.name"), "length")
        self.assertEqual(len(recorded["events"]), 1)
        evt = recorded["events"][0]
        self.assertEqual(evt.name, "gen_ai.evaluations")
        body_item = evt.body["evaluations"][0]
        self.assertEqual(body_item["gen_ai.evaluation.name"], "length")
        # restore
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
        results = handler.evaluate_llm(self.invocation)
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.metric_name, "deepeval")
        self.assertIsNotNone(res.error)
        self.assertEqual(len(recorded["events"]), 1)
        body_item = recorded["events"][0].body["evaluations"][0]
        self.assertEqual(body_item["gen_ai.evaluation.name"], "deepeval")
        self.assertIn("error.type", body_item)
        handler._event_logger.emit = original_emit  # restore


# ---------------- Span mode tests -----------------
class _SpanModeDummyEvaluator(Evaluator):
    def __init__(self, name: str, score: float):
        self._name = name
        self._score = score

    def evaluate_invocation(
        self, invocation: LLMInvocation
    ):  # pragma: no cover - trivial
        return EvaluationResult(
            metric_name=self._name, score=self._score, label="ok"
        )


class TestEvaluatorSpanModes(unittest.TestCase):
    def setUp(self):
        # isolate tracer provider
        self.span_exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.span_exporter))
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        reg._EVALUATORS.clear()  # pylint: disable=protected-access
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
        from opentelemetry.util.genai.evaluators.registry import (
            register_evaluator,
        )

        if "dummy" in eval_list:
            register_evaluator(
                "dummy", lambda: _SpanModeDummyEvaluator("dummy", 0.9)
            )
        if "dummy2" in eval_list:
            register_evaluator(
                "dummy2", lambda: _SpanModeDummyEvaluator("dummy2", 0.7)
            )
        handler = get_telemetry_handler(tracer_provider=self.provider)
        handler.start_llm(self.invocation)
        handler.stop_llm(self.invocation)
        handler.evaluate_llm(self.invocation)
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


# ---------------- DeepEval dynamic loading tests -----------------
class TestDeepEvalDynamicLoading(unittest.TestCase):
    """Test that deepeval evaluator is dynamically loaded when package is installed and configured via env var."""

    def setUp(self):
        # Clear any existing evaluators and handler
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        reg._EVALUATORS.clear()
        # Prepare invocation
        self.invocation = LLMInvocation(request_model="model-x")
        self.invocation.input_messages.append(
            InputMessage(role="user", parts=[Text(content="hello")])
        )
        self.invocation.output_messages.append(
            OutputMessage(
                role="assistant",
                parts=[Text(content="world")],
                finish_reason="stop",
            )
        )

    @patch.dict(
        os.environ,
        {
            OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE: "true",
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "deepeval",
        },
        clear=True,
    )
    def test_deepeval_dynamic_import(self):
        # Simulate external module
        class DummyDeepEval(Evaluator):
            def evaluate_invocation(self, invocation):
                return EvaluationResult(
                    metric_name="deepeval", score=0.75, label="ok"
                )

        dummy_mod = type(sys)("dummy_mod")
        dummy_mod.DeepEvalEvaluator = (
            lambda event_logger, tracer: DummyDeepEval()
        )
        # Patch importlib to return our dummy module for deepeval integration
        import importlib

        orig_import = importlib.import_module

        def fake_import(name, package=None):
            if name == "opentelemetry.util.genai.evals.deepeval":
                return dummy_mod
            return orig_import(name, package)

        with patch("importlib.import_module", fake_import):
            handler = get_telemetry_handler()
            results = handler.evaluate_llm(self.invocation)
        # Verify dynamic loading and execution
        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.metric_name, "deepeval")
        self.assertEqual(res.score, 0.75)
        self.assertEqual(res.label, "ok")
        self.assertIsNone(res.error)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
