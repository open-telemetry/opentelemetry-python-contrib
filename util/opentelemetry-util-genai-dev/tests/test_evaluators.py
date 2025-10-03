# Copyright The OpenTelemetry Authors
#
# Evaluator tests: registry behavior, event & metric emission, and span modes.

import importlib
import os
import unittest
from typing import Sequence
from unittest.mock import patch

from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE,
    OTEL_INSTRUMENTATION_GENAI_EVALUATORS,
)
from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util.genai.evaluators.registry import (
    clear_registry,
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


def _reload_builtin_evaluators() -> None:
    from opentelemetry.util.genai.evaluators import builtins as builtin_module

    importlib.reload(builtin_module)


# ---------------- Registry & basic evaluation tests -----------------
class _DummyEvaluator(Evaluator):
    def __init__(
        self,
        name: str = "dummy",
        score: float = 0.42,
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


class TestEvaluatorRegistry(unittest.TestCase):
    def setUp(self):
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        clear_registry()
        _reload_builtin_evaluators()
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
        register_evaluator(
            "dummy", lambda metrics=None: _DummyEvaluator(metrics=metrics)
        )
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
        register_evaluator(
            "dummy",
            lambda metrics=None: _DummyEvaluator(
                "dummy", 0.1, metrics=metrics
            ),
        )
        register_evaluator(
            "dummy2",
            lambda metrics=None: _DummyEvaluator(
                "dummy2", 0.2, metrics=metrics
            ),
        )
        names = list_evaluators()
        self.assertIn("dummy", names)
        self.assertIn("dummy2", names)


# ---------------- DeepEval dynamic loading tests -----------------
class TestDeepEvalDynamicLoading(unittest.TestCase):
    """Test that deepeval evaluator is dynamically loaded when package is installed and configured via env var."""

    def setUp(self):
        # Clear any existing evaluators and handler
        if hasattr(get_telemetry_handler, "_default_handler"):
            delattr(get_telemetry_handler, "_default_handler")
        clear_registry()
        _reload_builtin_evaluators()
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
            OTEL_INSTRUMENTATION_GENAI_EVALUATORS: "external(custom_metric)",
        },
        clear=True,
    )
    def test_entry_point_dynamic_loading(self):
        class DummyEntryEvaluator(Evaluator):
            def __init__(self, metrics=None):
                super().__init__(metrics)

            def default_metrics(self) -> Sequence[str]:  # pragma: no cover
                return ("external",)

            def evaluate_llm(self, invocation):  # pragma: no cover
                metric = self.metrics[0] if self.metrics else "external"
                return [
                    EvaluationResult(
                        metric_name=metric, score=0.75, label="ok"
                    )
                ]

        class FakeEntryPoint:
            def __init__(self, name, target):
                self.name = name
                self._target = target

            def load(self):
                return self._target

        fake_eps = [
            FakeEntryPoint(
                "external",
                lambda metrics=None: DummyEntryEvaluator(metrics),
            )
        ]

        with patch(
            "opentelemetry.util.genai.evaluators.registry.entry_points",
            return_value=fake_eps,
        ):
            handler = get_telemetry_handler()
            results = handler.evaluate_llm(self.invocation)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertEqual(res.metric_name, "custom_metric")
        self.assertEqual(res.score, 0.75)
        self.assertEqual(res.label, "ok")
        self.assertIsNone(res.error)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
