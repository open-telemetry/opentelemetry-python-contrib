from __future__ import annotations

from typing import Any, Optional

from opentelemetry.metrics import Histogram, Meter, get_meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)

from ..instruments import Instruments
from ..types import Error, LLMInvocation
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

    def start(self, obj: Any) -> None:  # no-op for metrics
        return None

    def finish(self, obj: Any) -> None:
        if isinstance(obj, LLMInvocation):
            invocation = obj
            metric_attrs = _get_metric_attributes(
                invocation.request_model,
                invocation.response_model_name,
                GenAI.GenAiOperationNameValues.CHAT.value,
                invocation.provider,
                invocation.attributes.get("framework"),
            )
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
            _record_duration(
                self._duration_histogram, invocation, metric_attrs
            )

    def error(self, error: Error, obj: Any) -> None:
        if isinstance(obj, LLMInvocation):
            invocation = obj
            metric_attrs = _get_metric_attributes(
                invocation.request_model,
                invocation.response_model_name,
                GenAI.GenAiOperationNameValues.CHAT.value,
                invocation.provider,
                invocation.attributes.get("framework"),
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
            _record_duration(
                self._duration_histogram, invocation, metric_attrs
            )

    def handles(self, obj: Any) -> bool:
        from ..types import LLMInvocation, ToolCall

        return isinstance(obj, (LLMInvocation, ToolCall))
