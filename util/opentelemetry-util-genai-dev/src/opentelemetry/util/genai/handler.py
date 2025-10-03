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

"""
Telemetry handler for GenAI invocations.

This module exposes the `TelemetryHandler` class, which manages the lifecycle of
GenAI (Generative AI) invocations and emits telemetry data (spans and related attributes).
It supports starting, stopping, and failing LLM invocations.

Classes:
    - TelemetryHandler: Manages GenAI invocation lifecycles and emits telemetry.

Functions:
    - get_telemetry_handler: Returns a singleton `TelemetryHandler` instance.

Usage:
    handler = get_telemetry_handler()

    # Create an invocation object with your request data
    invocation = LLMInvocation(
        request_model="my-model",
        input_messages=[...],
        provider="my-provider",
        attributes={"custom": "attr"},
    )

    # Start the invocation (opens a span)
    handler.start_llm(invocation)

    # Populate outputs and any additional attributes, then stop (closes the span)
    invocation.output_messages = [...]
    invocation.attributes.update({"more": "attrs"})
    handler.stop_llm(invocation)

    # Or, in case of error
    # handler.fail_llm(invocation, Error(type="...", message="..."))
"""

import os
import time
from typing import Any, Optional

from opentelemetry import _events as _otel_events
from opentelemetry import _logs
from opentelemetry import metrics as _metrics
from opentelemetry import trace as _trace_mod
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer
from opentelemetry.util.genai.emitters import (
    CompositeEvaluationEmitter,
    CompositeGenerator,
    ContentEventsEmitter,
    EvaluationEmitter,
    EvaluationEventsEmitter,
    EvaluationMetricsEmitter,
    EvaluationSpansEmitter,
    MetricsEmitter,
    SpanEmitter,
)
from opentelemetry.util.genai.plugins import (
    PluginEmitterBundle,
    load_emitter_plugin,
)
from opentelemetry.util.genai.types import (
    AgentInvocation,
    ContentCapturingMode,
    EmbeddingInvocation,
    Error,
    EvaluationResult,
    GenAI,
    LLMInvocation,
    Task,
    ToolCall,
    Workflow,
)
from opentelemetry.util.genai.utils import get_content_capturing_mode
from opentelemetry.util.genai.version import __version__

from .config import parse_env
from .environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from .evaluators.manager import EvaluationManager


class TelemetryHandler:
    """
    High-level handler managing GenAI invocation lifecycles and emitting
    them as spans, metrics, and events. Evaluation execution & emission is
    delegated to EvaluationManager for extensibility (mirrors emitter design).
    """

    def __init__(self, **kwargs: Any):
        tracer_provider = kwargs.get("tracer_provider")
        # Store provider reference for later identity comparison (test isolation)
        from opentelemetry import trace as _trace_mod_local

        self._tracer_provider_ref = (
            tracer_provider or _trace_mod_local.get_tracer_provider()
        )
        self._tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_36_0.value,
        )
        self._event_logger = _otel_events.get_event_logger(__name__)
        # Logger for content events (uses Logs API, not Events API)
        self._content_logger = _logs.get_logger(__name__)
        meter_provider = kwargs.get("meter_provider")
        self._meter_provider = meter_provider  # store for flushing in tests
        if meter_provider is not None:
            meter = meter_provider.get_meter(__name__)
        else:
            meter = _metrics.get_meter(__name__)
        # Single histogram for all evaluation scores (name stable across metrics)
        self._evaluation_histogram = meter.create_histogram(
            name="gen_ai.evaluation.score",
            unit="1",
            description="Scores produced by GenAI evaluators in [0,1] when applicable",
        )

        # Configuration: parse env only once
        settings = parse_env()
        # store settings for evaluation config
        self._settings = settings
        self._generator_kind = settings.generator_kind
        capture_span = settings.capture_content_span
        capture_span_traceloop = capture_span
        if not capture_span_traceloop:
            capture_flag = os.environ.get(
                OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, ""
            ).strip()
            if capture_flag.lower() in ("true", "1", "yes") and (
                settings.only_traceloop_compat
                or "traceloop_compat" in settings.extra_emitters
            ):
                capture_span_traceloop = True
        capture_events = settings.capture_content_events

        evaluation_emitters: list[EvaluationEmitter] = [
            EvaluationMetricsEmitter(self._evaluation_histogram),
            EvaluationEventsEmitter(self._event_logger),
        ]
        if settings.evaluation_span_mode in ("aggregated", "per_metric"):
            evaluation_emitters.append(
                EvaluationSpansEmitter(
                    tracer=self._tracer,
                    span_mode=settings.evaluation_span_mode,
                )
            )
        self._evaluation_emitter = CompositeEvaluationEmitter(
            evaluation_emitters
        )

        # Compose emitters based on parsed settings
        plugin_bundles: list[PluginEmitterBundle] = []
        replace_default_emitters = False
        for plugin_name in settings.extra_emitters:
            if plugin_name == "traceloop_compat":
                continue
            bundle = load_emitter_plugin(
                plugin_name,
                tracer=self._tracer,
                meter=meter,
                event_logger=self._event_logger,
                settings=settings,
            )
            if bundle:
                plugin_bundles.append(bundle)
                if bundle.replace_default_emitters:
                    replace_default_emitters = True

        emitters = []
        if settings.only_traceloop_compat:
            # Only traceloop compat requested
            from opentelemetry.util.genai.emitters import (
                TraceloopCompatEmitter,
            )

            traceloop_emitter = TraceloopCompatEmitter(
                tracer=self._tracer, capture_content=capture_span_traceloop
            )
            emitters.append(traceloop_emitter)
        else:
            if not replace_default_emitters:
                if settings.generator_kind == "span_metric_event":
                    span_emitter = SpanEmitter(
                        tracer=self._tracer,
                        capture_content=False,  # keep span lean
                    )
                    metrics_emitter = MetricsEmitter(meter=meter)
                    content_emitter = ContentEventsEmitter(
                        logger=self._content_logger,
                        capture_content=capture_events,
                    )
                    emitters.extend(
                        [span_emitter, metrics_emitter, content_emitter]
                    )
                elif settings.generator_kind == "span_metric":
                    span_emitter = SpanEmitter(
                        tracer=self._tracer,
                        capture_content=capture_span,
                    )
                    metrics_emitter = MetricsEmitter(meter=meter)
                    emitters.extend([span_emitter, metrics_emitter])
                else:
                    span_emitter = SpanEmitter(
                        tracer=self._tracer,
                        capture_content=capture_span,
                    )
                    emitters.append(span_emitter)
            # Append extra emitters if requested
            if "traceloop_compat" in settings.extra_emitters:
                try:
                    from opentelemetry.util.genai.emitters import (
                        TraceloopCompatEmitter,
                    )

                    traceloop_emitter = TraceloopCompatEmitter(
                        tracer=self._tracer,
                        capture_content=capture_span_traceloop,
                    )
                    emitters.append(traceloop_emitter)
                except Exception:  # pragma: no cover
                    pass
        for bundle in plugin_bundles:
            if bundle.emitters:
                emitters.extend(bundle.emitters)
        # Phase 1: wrap in composite (single element) to prepare for multi-emitter
        self._generator = CompositeGenerator(emitters)  # type: ignore[arg-type]

        # Instantiate evaluation manager (extensible evaluation pipeline)
        # TODO should use Logs API
        self._evaluation_manager = EvaluationManager(
            settings=settings,
            submit_results=self._handle_evaluation_results,
        )

    def _refresh_capture_content(
        self,
    ):  # re-evaluate env each start in case singleton created before patching
        try:
            mode = get_content_capturing_mode()
            emitters = getattr(self._generator, "_generators", [])  # type: ignore[attr-defined]
            # Determine new values for span-like emitters
            new_value_span = mode in (
                ContentCapturingMode.SPAN_ONLY,
                ContentCapturingMode.SPAN_AND_EVENT,
            )
            traceloop_requested = os.environ.get(
                OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, ""
            ).strip().lower() in ("true", "1", "yes")
            # For span_metric_event flavor we always keep span lean (never capture on span)
            if getattr(self, "_generator_kind", None) == "span_metric_event":
                new_value_span = False
            new_value_events = mode in (
                ContentCapturingMode.EVENT_ONLY,
                ContentCapturingMode.SPAN_AND_EVENT,
            )
            for em in emitters:
                role = getattr(em, "role", None)
                if role == "content_event" and hasattr(em, "_capture_content"):
                    try:
                        em._capture_content = new_value_events  # type: ignore[attr-defined]
                    except Exception:
                        pass
                elif role in ("span", "traceloop_compat") and hasattr(
                    em, "set_capture_content"
                ):
                    try:
                        desired = new_value_span
                        if not new_value_span and role == "traceloop_compat":
                            desired = traceloop_requested
                        em.set_capture_content(desired)  # type: ignore[attr-defined]
                    except Exception:
                        pass
        except Exception:
            pass

    def start_llm(
        self,
        invocation: LLMInvocation,
    ) -> LLMInvocation:
        """Start an LLM invocation and create a pending span entry."""
        # Ensure capture content settings are current
        self._refresh_capture_content()
        # Start invocation span; tracer context propagation handles parent/child links
        self._generator.start(invocation)
        return invocation

    def stop_llm(self, invocation: LLMInvocation) -> LLMInvocation:
        """Finalize an LLM invocation successfully and end its span."""
        invocation.end_time = time.time()
        self._generator.finish(invocation)
        # Automatic async evaluation sampling (non-blocking)
        try:
            manager = getattr(self, "_evaluation_manager", None)
            if manager and manager.should_evaluate(invocation):  # type: ignore[attr-defined]
                scheduled = manager.offer(invocation)  # type: ignore[attr-defined]
                if scheduled:
                    invocation.attributes.setdefault(
                        "gen_ai.evaluation.executed", True
                    )
        except Exception:
            pass
        # Force flush metrics if a custom provider with force_flush is present
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover - defensive
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return invocation

    def fail_llm(
        self, invocation: LLMInvocation, error: Error
    ) -> LLMInvocation:
        """Fail an LLM invocation and end its span with error status."""
        invocation.end_time = time.time()
        self._generator.error(error, invocation)
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return invocation

    def start_embedding(
        self, invocation: EmbeddingInvocation
    ) -> EmbeddingInvocation:
        """Start an embedding invocation and create a pending span entry."""
        self._refresh_capture_content()
        invocation.start_time = time.time()
        self._generator.start(invocation)
        return invocation

    def stop_embedding(
        self, invocation: EmbeddingInvocation
    ) -> EmbeddingInvocation:
        """Finalize an embedding invocation successfully and end its span."""
        invocation.end_time = time.time()
        self._generator.finish(invocation)
        # Force flush metrics if a custom provider with force_flush is present
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return invocation

    def fail_embedding(
        self, invocation: EmbeddingInvocation, error: Error
    ) -> EmbeddingInvocation:
        """Fail an embedding invocation and end its span with error status."""
        invocation.end_time = time.time()
        self._generator.error(error, invocation)
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return invocation

    # ToolCall lifecycle --------------------------------------------------
    def start_tool_call(self, invocation: ToolCall) -> ToolCall:
        """Start a tool call invocation and create a pending span entry."""
        self._generator.start(invocation)
        return invocation

    def stop_tool_call(self, invocation: ToolCall) -> ToolCall:
        """Finalize a tool call invocation successfully and end its span."""
        invocation.end_time = time.time()
        self._generator.finish(invocation)
        return invocation

    def fail_tool_call(self, invocation: ToolCall, error: Error) -> ToolCall:
        """Fail a tool call invocation and end its span with error status."""
        invocation.end_time = time.time()
        self._generator.error(error, invocation)
        return invocation

    # Workflow lifecycle --------------------------------------------------
    def start_workflow(self, workflow: Workflow) -> Workflow:
        """Start a workflow and create a pending span entry."""
        self._refresh_capture_content()
        self._generator.start(workflow)
        return workflow

    def _handle_evaluation_results(
        self, invocation: GenAI, results: list[EvaluationResult]
    ) -> None:
        if not results:
            return
        try:
            self._evaluation_emitter.emit(results, invocation)
        except Exception:  # pragma: no cover - defensive
            pass

    def stop_workflow(self, workflow: Workflow) -> Workflow:
        """Finalize a workflow successfully and end its span."""
        workflow.end_time = time.time()
        self._generator.finish(workflow)
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return workflow

    def fail_workflow(self, workflow: Workflow, error: Error) -> Workflow:
        """Fail a workflow and end its span with error status."""
        workflow.end_time = time.time()
        self._generator.error(error, workflow)
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return workflow

    # Agent lifecycle -----------------------------------------------------
    def start_agent(self, agent: AgentInvocation) -> AgentInvocation:
        """Start an agent operation (create or invoke) and create a pending span entry."""
        self._refresh_capture_content()
        self._generator.start(agent)
        return agent

    def stop_agent(self, agent: AgentInvocation) -> AgentInvocation:
        """Finalize an agent operation successfully and end its span."""
        agent.end_time = time.time()
        self._generator.finish(agent)
        # Automatic async evaluation if configured for agents
        try:
            manager = getattr(self, "_evaluation_manager", None)
            if manager and manager.should_evaluate(agent):  # type: ignore[attr-defined]
                scheduled = manager.offer(agent)  # type: ignore[attr-defined]
                if scheduled:
                    agent.attributes.setdefault(
                        "gen_ai.evaluation.executed", True
                    )
        except Exception:
            pass
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return agent

    def fail_agent(
        self, agent: AgentInvocation, error: Error
    ) -> AgentInvocation:
        """Fail an agent operation and end its span with error status."""
        agent.end_time = time.time()
        self._generator.error(error, agent)
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return agent

    # Task lifecycle ------------------------------------------------------
    def start_task(self, task: Task) -> Task:
        """Start a task and create a pending span entry."""
        self._refresh_capture_content()
        self._generator.start(task)
        return task

    def stop_task(self, task: Task) -> Task:
        """Finalize a task successfully and end its span."""
        task.end_time = time.time()
        self._generator.finish(task)
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return task

    def fail_task(self, task: Task, error: Error) -> Task:
        """Fail a task and end its span with error status."""
        task.end_time = time.time()
        self._generator.error(error, task)
        if (
            hasattr(self, "_meter_provider")
            and self._meter_provider is not None
        ):
            try:  # pragma: no cover
                self._meter_provider.force_flush()  # type: ignore[attr-defined]
            except Exception:
                pass
        return task

    def evaluate_llm(
        self,
        invocation: LLMInvocation,
        evaluators: Optional[list[str]] = None,
    ) -> list[EvaluationResult]:
        """Proxy to EvaluationManager for running evaluators.

        Retained public signature for backward compatibility. The underlying
        implementation has been refactored into EvaluationManager to allow
        pluggable emission similar to emitters.
        """
        return self._evaluation_manager.evaluate(invocation, evaluators)  # type: ignore[arg-type]

    def wait_for_evaluations(self, timeout: Optional[float] = None) -> None:
        """Wait for all pending evaluations to complete, up to the specified timeout.

        This is primarily intended for use in test scenarios to ensure that
        all asynchronous evaluation tasks have finished before assertions are made.
        """
        # TODO: implment
        self._evaluation_manager.wait_for_all(timeout)  # type: ignore[attr-defined]

    # Generic lifecycle API ------------------------------------------------
    def start(self, obj: Any) -> Any:
        """Generic start method for any invocation type."""
        if isinstance(obj, Workflow):
            return self.start_workflow(obj)
        if isinstance(obj, AgentInvocation):
            return self.start_agent(obj)
        if isinstance(obj, Task):
            return self.start_task(obj)
        if isinstance(obj, LLMInvocation):
            return self.start_llm(obj)
        if isinstance(obj, EmbeddingInvocation):
            return self.start_embedding(obj)
        if isinstance(obj, ToolCall):
            return self.start_tool_call(obj)
        return obj

    def finish(self, obj: Any) -> Any:
        """Generic finish method for any invocation type."""
        if isinstance(obj, Workflow):
            return self.stop_workflow(obj)
        if isinstance(obj, AgentInvocation):
            return self.stop_agent(obj)
        if isinstance(obj, Task):
            return self.stop_task(obj)
        if isinstance(obj, LLMInvocation):
            return self.stop_llm(obj)
        if isinstance(obj, EmbeddingInvocation):
            return self.stop_embedding(obj)
        if isinstance(obj, ToolCall):
            return self.stop_tool_call(obj)
        return obj

    def fail(self, obj: Any, error: Error) -> Any:
        """Generic fail method for any invocation type."""
        if isinstance(obj, Workflow):
            return self.fail_workflow(obj, error)
        if isinstance(obj, AgentInvocation):
            return self.fail_agent(obj, error)
        if isinstance(obj, Task):
            return self.fail_task(obj, error)
        if isinstance(obj, LLMInvocation):
            return self.fail_llm(obj, error)
        if isinstance(obj, EmbeddingInvocation):
            return self.fail_embedding(obj, error)
        if isinstance(obj, ToolCall):
            return self.fail_tool_call(obj, error)
        return obj


def get_telemetry_handler(**kwargs: Any) -> TelemetryHandler:
    """
    Returns a singleton TelemetryHandler instance. If the global tracer provider
    has changed since the handler was created, a new handler is instantiated so that
    spans are recorded with the active provider (important for test isolation).
    """
    handler: Optional[TelemetryHandler] = getattr(
        get_telemetry_handler, "_default_handler", None
    )
    current_provider = _trace_mod.get_tracer_provider()
    requested_provider = kwargs.get("tracer_provider")
    target_provider = requested_provider or current_provider
    recreate = False
    if handler is not None:
        # Recreate if provider changed or handler lacks provider reference (older instance)
        if not hasattr(handler, "_tracer_provider_ref"):
            recreate = True
        elif handler._tracer_provider_ref is not target_provider:  # type: ignore[attr-defined]
            recreate = True
    if handler is None or recreate:
        handler = TelemetryHandler(**kwargs)
        setattr(get_telemetry_handler, "_default_handler", handler)
    return handler
