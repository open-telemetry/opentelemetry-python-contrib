from __future__ import annotations

from typing import Any, Optional

from opentelemetry.metrics import Histogram, Meter, get_meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)

from ..attributes import GEN_AI_AGENT_ID, GEN_AI_AGENT_NAME
from ..instruments import Instruments
from ..types import AgentInvocation, Error, LLMInvocation, Task, Workflow
from .utils import (
    _get_metric_attributes,
    _record_duration,
    _record_token_metrics,
)


class MetricsEmitter:
    """Emits GenAI metrics (duration + token usage).

    Ignores objects that are not LLMInvocation (e.g., EmbeddingInvocation for now).
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

    def start(self, obj: Any) -> None:  # no-op for metrics
        return None

    def finish(self, obj: Any) -> None:
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
                GenAI.GenAiOperationNameValues.CHAT.value,
                invocation.provider,
                invocation.attributes.get("framework"),
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GEN_AI_AGENT_ID] = invocation.agent_id

            _record_token_metrics(
                self._token_histogram,
                invocation.input_tokens,
                invocation.output_tokens,
                metric_attrs,
            )
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
                "tool_call",
                invocation.provider,
                None,
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GEN_AI_AGENT_ID] = invocation.agent_id

            _record_duration(
                self._duration_histogram, invocation, metric_attrs
            )

    def error(self, error: Error, obj: Any) -> None:
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
                GenAI.GenAiOperationNameValues.CHAT.value,
                invocation.provider,
                invocation.attributes.get("framework"),
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GEN_AI_AGENT_ID] = invocation.agent_id

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
                "tool_call",
                invocation.provider,
                None,
            )
            # Add agent context if available
            if invocation.agent_name:
                metric_attrs[GEN_AI_AGENT_NAME] = invocation.agent_name
            if invocation.agent_id:
                metric_attrs[GEN_AI_AGENT_ID] = invocation.agent_id

            _record_duration(
                self._duration_histogram, invocation, metric_attrs
            )

    def handles(self, obj: Any) -> bool:
        from ..types import LLMInvocation, ToolCall

        return isinstance(
            obj,
            (LLMInvocation, ToolCall, Workflow, AgentInvocation, Task),
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

        self._workflow_duration_histogram.record(
            duration, attributes=metric_attrs
        )

    def _record_agent_metrics(self, agent: AgentInvocation) -> None:
        """Record metrics for an agent operation."""
        if agent.end_time is None:
            return
        duration = agent.end_time - agent.start_time
        metric_attrs = {
            "gen_ai.operation.name": f"agent.{agent.operation}",
            "gen_ai.agent.name": agent.name,
            "gen_ai.agent.id": str(agent.run_id),
        }
        if agent.agent_type:
            metric_attrs["gen_ai.agent.type"] = agent.agent_type
        if agent.framework:
            metric_attrs["gen_ai.framework"] = agent.framework

        self._agent_duration_histogram.record(
            duration, attributes=metric_attrs
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
            metric_attrs["gen_ai.agent.name"] = task.assigned_agent

        self._task_duration_histogram.record(duration, attributes=metric_attrs)
