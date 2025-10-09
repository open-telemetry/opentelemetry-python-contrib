from __future__ import annotations

from typing import Any, Optional

from opentelemetry import trace
from opentelemetry.metrics import Histogram, Meter, get_meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)

from ..instruments import Instruments
from ..interfaces import EmitterMeta
from ..types import (
    AgentInvocation,
    EmbeddingInvocation,
    Error,
    LLMInvocation,
    Task,
    Workflow,
)
from .utils import (
    _get_metric_attributes,
    _record_duration,
    _record_token_metrics,
)


class MetricsEmitter(EmitterMeta):
    """Emits GenAI metrics (duration + token usage).

    Supports LLMInvocation, EmbeddingInvocation, ToolCall, Workflow, Agent, and Task.
    """

    role = "metric"
    name = "semconv_metrics"

    def __init__(self, meter: Optional[Meter] = None):
        _meter: Meter = meter or get_meter(__name__)
        instruments = Instruments(_meter)
        self._duration_histogram: Histogram = (
            instruments.operation_duration_histogram
        )
        self._token_histogram: Histogram = instruments.token_usage_histogram
        self._workflow_duration_histogram: Histogram = (
            instruments.workflow_duration_histogram
        )
        self._agent_duration_histogram: Histogram = (
            instruments.agent_duration_histogram
        )
        self._task_duration_histogram: Histogram = (
            instruments.task_duration_histogram
        )

    def on_start(self, obj: Any) -> None:  # no-op for metrics
        return None

    def on_end(self, obj: Any) -> None:
        if isinstance(obj, Workflow):
            self._record_workflow_metrics(obj)
            return
        if isinstance(obj, AgentInvocation):
            self._record_agent_metrics(obj)
            return
        if isinstance(obj, Task):
            self._record_task_metrics(obj)
            return

        if isinstance(obj, LLMInvocation):
            invocation = obj
            metric_attrs = _get_metric_attributes(
                invocation.request_model,
                invocation.response_model_name,
                invocation.operation,
                invocation.provider,
                invocation.framework,
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GenAI.GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GenAI.GEN_AI_AGENT_ID] = invocation.agent_id

            _record_token_metrics(
                self._token_histogram,
                invocation.input_tokens,
                invocation.output_tokens,
                metric_attrs,
                span=getattr(invocation, "span", None),
            )
            _record_duration(
                self._duration_histogram,
                invocation,
                metric_attrs,
                span=getattr(invocation, "span", None),
            )
            return
        from ..types import ToolCall

        if isinstance(obj, ToolCall):
            invocation = obj
            metric_attrs = _get_metric_attributes(
                invocation.name,
                None,
                GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value,
                invocation.provider,
                invocation.framework,
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GenAI.GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GenAI.GEN_AI_AGENT_ID] = invocation.agent_id

            _record_duration(
                self._duration_histogram,
                invocation,
                metric_attrs,
                span=getattr(invocation, "span", None),
            )

        if isinstance(obj, EmbeddingInvocation):
            invocation = obj
            metric_attrs = _get_metric_attributes(
                invocation.request_model,
                None,
                invocation.operation_name,
                invocation.provider,
                invocation.framework,
                server_address=invocation.server_address,
                server_port=invocation.server_port,
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GenAI.GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GenAI.GEN_AI_AGENT_ID] = invocation.agent_id

            _record_duration(
                self._duration_histogram,
                invocation,
                metric_attrs,
                span=getattr(invocation, "span", None),
            )

    def on_error(self, error: Error, obj: Any) -> None:
        # Handle new agentic types
        if isinstance(obj, Workflow):
            self._record_workflow_metrics(obj)
            return
        if isinstance(obj, AgentInvocation):
            self._record_agent_metrics(obj)
            return
        if isinstance(obj, Task):
            self._record_task_metrics(obj)
            return

        # Handle existing types with agent context
        if isinstance(obj, LLMInvocation):
            invocation = obj
            metric_attrs = _get_metric_attributes(
                invocation.request_model,
                invocation.response_model_name,
                invocation.operation,
                invocation.provider,
                invocation.framework,
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GenAI.GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GenAI.GEN_AI_AGENT_ID] = invocation.agent_id

            _record_duration(
                self._duration_histogram, invocation, metric_attrs
            )
            return
        from ..types import ToolCall

        if isinstance(obj, ToolCall):
            invocation = obj
            metric_attrs = _get_metric_attributes(
                invocation.name,
                None,
                GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value,
                invocation.provider,
                invocation.framework,
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GenAI.GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GenAI.GEN_AI_AGENT_ID] = invocation.agent_id

            _record_duration(
                self._duration_histogram,
                invocation,
                metric_attrs,
                span=getattr(invocation, "span", None),
            )

        if isinstance(obj, EmbeddingInvocation):
            invocation = obj
            metric_attrs = _get_metric_attributes(
                invocation.request_model,
                None,
                invocation.operation_name,
                invocation.provider,
                invocation.framework,
                server_address=invocation.server_address,
                server_port=invocation.server_port,
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GenAI.GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GenAI.GEN_AI_AGENT_ID] = invocation.agent_id

            _record_duration(
                self._duration_histogram,
                invocation,
                metric_attrs,
                span=getattr(invocation, "span", None),
            )

    def handles(self, obj: Any) -> bool:
        from ..types import LLMInvocation, ToolCall

        return isinstance(
            obj,
            (
                LLMInvocation,
                ToolCall,
                Workflow,
                AgentInvocation,
                Task,
                EmbeddingInvocation,
            ),
        )

    # Helper methods for new agentic types
    def _record_workflow_metrics(self, workflow: Workflow) -> None:
        """Record metrics for a workflow."""
        if workflow.end_time is None:
            return
        duration = workflow.end_time - workflow.start_time
        metric_attrs = {
            "gen_ai.workflow.name": workflow.name,
        }
        if workflow.workflow_type:
            metric_attrs["gen_ai.workflow.type"] = workflow.workflow_type
        if workflow.framework:
            metric_attrs["gen_ai.framework"] = workflow.framework

        context = None
        span = getattr(workflow, "span", None)
        if span is not None:
            try:
                context = trace.set_span_in_context(span)
            except Exception:  # pragma: no cover - defensive
                context = None

        self._workflow_duration_histogram.record(
            duration, attributes=metric_attrs, context=context
        )

    def _record_agent_metrics(self, agent: AgentInvocation) -> None:
        """Record metrics for an agent operation."""
        if agent.end_time is None:
            return
        duration = agent.end_time - agent.start_time
        metric_attrs = {
            GenAI.GEN_AI_OPERATION_NAME: agent.operation,
            GenAI.GEN_AI_AGENT_NAME: agent.name,
            GenAI.GEN_AI_AGENT_ID: str(agent.run_id),
        }
        if agent.agent_type:
            metric_attrs["gen_ai.agent.type"] = agent.agent_type
        if agent.framework:
            metric_attrs["gen_ai.framework"] = agent.framework

        context = None
        span = getattr(agent, "span", None)
        if span is not None:
            try:
                context = trace.set_span_in_context(span)
            except Exception:  # pragma: no cover - defensive
                context = None

        self._agent_duration_histogram.record(
            duration, attributes=metric_attrs, context=context
        )

    def _record_task_metrics(self, task: Task) -> None:
        """Record metrics for a task."""
        if task.end_time is None:
            return
        duration = task.end_time - task.start_time
        metric_attrs = {
            "gen_ai.task.name": task.name,
        }
        if task.task_type:
            metric_attrs["gen_ai.task.type"] = task.task_type
        if task.source:
            metric_attrs["gen_ai.task.source"] = task.source
        if task.assigned_agent:
            metric_attrs[GenAI.GEN_AI_AGENT_NAME] = task.assigned_agent

        context = None
        span = getattr(task, "span", None)
        if span is not None:
            try:
                context = trace.set_span_in_context(span)
            except Exception:  # pragma: no cover - defensive
                context = None

        self._task_duration_histogram.record(
            duration, attributes=metric_attrs, context=context
        )
