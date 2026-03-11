# pylint: skip-file

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from itertools import count
from typing import Any, Mapping, Sequence

from .processor_interface import TracingProcessor
from .spans import Span
from .traces import Trace

SPAN_TYPE_AGENT = "agent"
SPAN_TYPE_FUNCTION = "function"
SPAN_TYPE_GENERATION = "generation"
SPAN_TYPE_RESPONSE = "response"

__all__ = [
    "TraceProvider",
    "get_trace_provider",
    "set_trace_processors",
    "trace",
    "agent_span",
    "generation_span",
    "function_span",
    "response_span",
    "AgentSpanData",
    "GenerationSpanData",
    "FunctionSpanData",
    "ResponseSpanData",
]


@dataclass
class AgentSpanData:
    name: str | None = None
    handoffs: list[str] | None = None
    tools: list[str] | None = None
    output_type: str | None = None

    @property
    def type(self) -> str:
        return SPAN_TYPE_AGENT


@dataclass
class FunctionSpanData:
    name: str | None = None
    input: Any = None
    output: Any = None

    @property
    def type(self) -> str:
        return SPAN_TYPE_FUNCTION


@dataclass
class GenerationSpanData:
    input: Sequence[Mapping[str, Any]] | None = None
    output: Sequence[Mapping[str, Any]] | None = None
    model: str | None = None
    model_config: Mapping[str, Any] | None = None
    usage: Mapping[str, Any] | None = None

    @property
    def type(self) -> str:
        return SPAN_TYPE_GENERATION


@dataclass
class ResponseSpanData:
    response: Any = None

    @property
    def type(self) -> str:
        return SPAN_TYPE_RESPONSE


class _ProcessorFanout(TracingProcessor):
    def __init__(self) -> None:
        self._processors: list[TracingProcessor] = []

    def add_tracing_processor(self, processor: TracingProcessor) -> None:
        self._processors.append(processor)

    def set_processors(self, processors: list[TracingProcessor]) -> None:
        self._processors = list(processors)

    def on_trace_start(self, trace: Trace) -> None:
        for processor in list(self._processors):
            processor.on_trace_start(trace)

    def on_trace_end(self, trace: Trace) -> None:
        for processor in list(self._processors):
            processor.on_trace_end(trace)

    def on_span_start(self, span: Span) -> None:
        for processor in list(self._processors):
            processor.on_span_start(span)

    def on_span_end(self, span: Span) -> None:
        for processor in list(self._processors):
            processor.on_span_end(span)

    def shutdown(self) -> None:
        for processor in list(self._processors):
            processor.shutdown()

    def force_flush(self) -> None:
        for processor in list(self._processors):
            processor.force_flush()


class TraceProvider:
    def __init__(self) -> None:
        self._multi_processor = _ProcessorFanout()
        self._ids = count(1)

    def register_processor(self, processor: TracingProcessor) -> None:
        self._multi_processor.add_tracing_processor(processor)

    def set_processors(self, processors: list[TracingProcessor]) -> None:
        self._multi_processor.set_processors(processors)

    def create_trace(
        self,
        name: str,
        trace_id: str | None = None,
        group_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        disabled: bool = False,
    ) -> Trace:
        trace_id = trace_id or f"trace_{next(self._ids)}"
        return Trace(name, trace_id, self._multi_processor)

    def create_span(
        self,
        span_data: Any,
        span_id: str | None = None,
        parent: Trace | Span | None = None,
        disabled: bool = False,
    ) -> Span:
        span_id = span_id or f"span_{next(self._ids)}"
        if isinstance(parent, Span):
            trace_id = parent.trace_id
            parent_id = parent.span_id
        elif isinstance(parent, Trace):
            trace_id = parent.trace_id
            parent_id = None
        else:
            trace_id = f"trace_{next(self._ids)}"
            parent_id = None
        return Span(
            trace_id, span_id, span_data, parent_id, self._multi_processor
        )

    def shutdown(self) -> None:
        self._multi_processor.shutdown()


_PROVIDER = TraceProvider()
_CURRENT_TRACE: Trace | None = None


def get_trace_provider() -> TraceProvider:
    return _PROVIDER


def set_trace_processors(processors: list[TracingProcessor]) -> None:
    _PROVIDER.set_processors(processors)


@contextmanager
def trace(name: str, **kwargs: Any):
    global _CURRENT_TRACE
    trace_obj = _PROVIDER.create_trace(name, **kwargs)
    previous = _CURRENT_TRACE
    _CURRENT_TRACE = trace_obj
    trace_obj.start()
    try:
        yield trace_obj
    finally:
        trace_obj.finish()
        _CURRENT_TRACE = previous


@contextmanager
def generation_span(**kwargs: Any):
    data = GenerationSpanData(**kwargs)
    span = _PROVIDER.create_span(data, parent=_CURRENT_TRACE)
    span.start()
    try:
        yield span
    finally:
        span.finish()


@contextmanager
def agent_span(
    name: str,
    handoffs: list[str] | None = None,
    tools: list[str] | None = None,
    output_type: str | None = None,
    **kwargs: Any,
):
    data = AgentSpanData(
        name=name, handoffs=handoffs, tools=tools, output_type=output_type
    )
    span = _PROVIDER.create_span(data, parent=_CURRENT_TRACE)
    span.start()
    try:
        yield span
    finally:
        span.finish()


@contextmanager
def function_span(**kwargs: Any):
    data = FunctionSpanData(**kwargs)
    span = _PROVIDER.create_span(data, parent=_CURRENT_TRACE)
    span.start()
    try:
        yield span
    finally:
        span.finish()


@contextmanager
def response_span(**kwargs: Any):
    data = ResponseSpanData(**kwargs)
    span = _PROVIDER.create_span(data, parent=_CURRENT_TRACE)
    span.start()
    try:
        yield span
    finally:
        span.finish()
