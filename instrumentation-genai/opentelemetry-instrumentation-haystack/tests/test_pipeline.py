# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for the Haystack pipeline instrumentation.

These build real Haystack pipelines from a trivial custom component and run
them locally, with no LLM provider or network access, so the workflow span
emitted by ``opentelemetry-util-genai`` can be asserted directly.
"""

from __future__ import annotations

import pytest
from haystack import AsyncPipeline, Pipeline, component
from haystack.core.errors import PipelineRuntimeError
from haystack.core.pipeline.async_pipeline import (
    AsyncPipeline as _AsyncPipelineImpl,
)
from haystack.core.pipeline.pipeline import Pipeline as _PipelineImpl

from opentelemetry.instrumentation.haystack import HaystackInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode

_EXPECTED_OPERATION_NAME = "invoke_workflow"
_EXPECTED_SPAN_NAME = "invoke_workflow haystack.pipeline"


@component
class Doubler:
    """Trivial offline component: doubles its integer input."""

    @component.output_types(value=int)
    def run(self, value: int) -> dict[str, int]:
        return {"value": value * 2}


@component
class Boom:
    """Trivial offline component whose run always raises."""

    @component.output_types(value=int)
    def run(self, value: int) -> dict[str, int]:
        raise ValueError("boom from component")


def _build_sync_pipeline(component_instance: object) -> Pipeline:
    pipeline = Pipeline()
    pipeline.add_component("comp", component_instance)
    return pipeline


def _build_async_pipeline(component_instance: object) -> AsyncPipeline:
    pipeline = AsyncPipeline()
    pipeline.add_component("comp", component_instance)
    return pipeline


def test_pipeline_run_emits_workflow_span(instrument, span_exporter):
    pipeline = _build_sync_pipeline(Doubler())

    result = pipeline.run({"comp": {"value": 21}})

    assert result == {"comp": {"value": 42}}

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == _EXPECTED_SPAN_NAME
    assert span.kind == SpanKind.INTERNAL
    assert span.status.status_code == StatusCode.UNSET

    operation_name = span.attributes[GenAI.GEN_AI_OPERATION_NAME]
    assert operation_name == _EXPECTED_OPERATION_NAME
    assert isinstance(operation_name, str)

    assert error_attributes.ERROR_TYPE not in span.attributes


def test_pipeline_run_error_sets_error_status_and_reraises(
    instrument, span_exporter
):
    pipeline = _build_sync_pipeline(Boom())

    with pytest.raises(PipelineRuntimeError) as exc_info:
        pipeline.run({"comp": {"value": 1}})

    # Original exception (Haystack wraps the component error) is re-raised.
    assert "boom from component" in str(exc_info.value)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == _EXPECTED_SPAN_NAME
    assert span.status.status_code == StatusCode.ERROR

    error_type = span.attributes[error_attributes.ERROR_TYPE]
    assert error_type == PipelineRuntimeError.__qualname__
    assert isinstance(error_type, str)

    assert (
        span.attributes[GenAI.GEN_AI_OPERATION_NAME]
        == _EXPECTED_OPERATION_NAME
    )


@pytest.mark.asyncio
async def test_async_pipeline_run_emits_workflow_span(
    instrument, span_exporter
):
    pipeline = _build_async_pipeline(Doubler())

    result = await pipeline.run_async({"comp": {"value": 5}})

    assert result == {"comp": {"value": 10}}

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.name == _EXPECTED_SPAN_NAME
    assert span.kind == SpanKind.INTERNAL
    assert span.status.status_code == StatusCode.UNSET
    assert (
        span.attributes[GenAI.GEN_AI_OPERATION_NAME]
        == _EXPECTED_OPERATION_NAME
    )


@pytest.mark.asyncio
async def test_async_pipeline_run_error_sets_error_status_and_reraises(
    instrument, span_exporter
):
    pipeline = _build_async_pipeline(Boom())

    with pytest.raises(PipelineRuntimeError) as exc_info:
        await pipeline.run_async({"comp": {"value": 1}})

    assert "boom from component" in str(exc_info.value)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]

    assert span.status.status_code == StatusCode.ERROR
    assert (
        span.attributes[error_attributes.ERROR_TYPE]
        == PipelineRuntimeError.__qualname__
    )


def test_instrument_sets_wrap_markers(instrument):
    # While instrumented, wrapt exposes the original via __wrapped__.
    assert hasattr(_PipelineImpl.run, "__wrapped__")
    assert hasattr(_AsyncPipelineImpl.run_async, "__wrapped__")


def test_uninstrument_removes_wrap_markers():
    instrumentor = HaystackInstrumentor()
    instrumentor.instrument()

    assert hasattr(_PipelineImpl.run, "__wrapped__")
    assert hasattr(_AsyncPipelineImpl.run_async, "__wrapped__")

    instrumentor.uninstrument()

    assert not hasattr(_PipelineImpl.run, "__wrapped__")
    assert not hasattr(_AsyncPipelineImpl.run_async, "__wrapped__")


def test_uninstrumented_pipeline_emits_no_span(span_exporter):
    """After uninstrumenting, running a pipeline emits no workflow span."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))

    instrumentor = HaystackInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    instrumentor.uninstrument()

    pipeline = _build_sync_pipeline(Doubler())
    result = pipeline.run({"comp": {"value": 3}})

    assert result == {"comp": {"value": 6}}
    assert span_exporter.get_finished_spans() == ()
