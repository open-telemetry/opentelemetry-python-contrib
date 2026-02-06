"""Tests for chain execution spans in LangChain instrumentation."""

from uuid import uuid4

import pytest

from opentelemetry.instrumentation.langchain.callback_handler import (
    OpenTelemetryLangChainCallbackHandler,
)
from opentelemetry.trace import SpanKind


@pytest.fixture
def callback_handler(tracer_provider):
    tracer = tracer_provider.get_tracer("test")
    return OpenTelemetryLangChainCallbackHandler(tracer=tracer)


def test_basic_chain_span(callback_handler, span_exporter):
    """Test that chains create proper spans."""
    run_id = uuid4()
    parent_run_id = uuid4()

    # Start a chain
    callback_handler.on_chain_start(
        serialized={"name": "TestChain"},
        inputs={"question": "What is 2 + 2?"},
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # End the chain
    callback_handler.on_chain_end(
        outputs={"answer": "4"},
        run_id=run_id,
        parent_run_id=parent_run_id,
    )

    # Verify the span
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]
    assert span.name == "chain TestChain"
    assert span.kind == SpanKind.INTERNAL


def test_nested_chains(callback_handler, span_exporter):
    """Test that nested chains create proper parent-child relationships."""
    parent_chain_id = uuid4()
    child_chain_id = uuid4()

    # Start parent chain
    callback_handler.on_chain_start(
        serialized={"name": "ParentChain"},
        inputs={"input": "parent input"},
        run_id=parent_chain_id,
        parent_run_id=None,
    )

    # Start child chain
    callback_handler.on_chain_start(
        serialized={"name": "ChildChain"},
        inputs={"input": "child input"},
        run_id=child_chain_id,
        parent_run_id=parent_chain_id,
    )

    # End child chain
    callback_handler.on_chain_end(
        outputs={"output": "child output"},
        run_id=child_chain_id,
        parent_run_id=parent_chain_id,
    )

    # End parent chain
    callback_handler.on_chain_end(
        outputs={"output": "parent output"},
        run_id=parent_chain_id,
        parent_run_id=None,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 2

    # Find the spans
    parent_span = next(s for s in spans if "ParentChain" in s.name)
    child_span = next(s for s in spans if "ChildChain" in s.name)

    assert parent_span.name == "chain ParentChain"
    assert child_span.name == "chain ChildChain"

    # The child should have been ended before the parent
    assert child_span.parent is not None


def test_chain_name_extraction_fallbacks(callback_handler, span_exporter):
    """Test various methods for extracting chain names."""

    # Test 1: Name from kwargs in serialized
    run_id1 = uuid4()
    callback_handler.on_chain_start(
        serialized={"kwargs": {"name": "KwargsChain"}},
        inputs={"input": "test"},
        run_id=run_id1,
    )
    callback_handler.on_chain_end(outputs={"output": "result"}, run_id=run_id1)

    # Test 2: Name from kwargs parameter
    run_id2 = uuid4()
    callback_handler.on_chain_start(
        serialized={},
        inputs={"input": "test"},
        run_id=run_id2,
        name="DirectKwargsChain",
    )
    callback_handler.on_chain_end(outputs={"output": "result"}, run_id=run_id2)

    # Test 3: Name from serialized name field
    run_id3 = uuid4()
    callback_handler.on_chain_start(
        serialized={"name": "SerializedNameChain"},
        inputs={"input": "test"},
        run_id=run_id3,
    )
    callback_handler.on_chain_end(outputs={"output": "result"}, run_id=run_id3)

    # Test 4: Name from serialized id (last element)
    run_id4 = uuid4()
    callback_handler.on_chain_start(
        serialized={"id": ["langchain", "chains", "IdChain"]},
        inputs={"input": "test"},
        run_id=run_id4,
    )
    callback_handler.on_chain_end(outputs={"output": "result"}, run_id=run_id4)

    # Test 5: Fallback to "unknown"
    run_id5 = uuid4()
    callback_handler.on_chain_start(
        serialized={},
        inputs={"input": "test"},
        run_id=run_id5,
    )
    callback_handler.on_chain_end(outputs={"output": "result"}, run_id=run_id5)

    # Verify all spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 5

    span_names = [span.name for span in spans]
    assert "chain KwargsChain" in span_names
    assert "chain DirectKwargsChain" in span_names
    assert "chain SerializedNameChain" in span_names
    assert "chain IdChain" in span_names
    assert "chain unknown" in span_names


def test_chain_with_nested_structure(callback_handler, span_exporter):
    """Test a complex chain with nested chains."""
    main_chain_id = uuid4()
    sub_chain1_id = uuid4()
    sub_chain2_id = uuid4()

    # Start the main chain
    callback_handler.on_chain_start(
        serialized={"name": "MainChain"},
        inputs={"query": "complex task"},
        run_id=main_chain_id,
    )

    # First sub-chain
    callback_handler.on_chain_start(
        serialized={"name": "SubChain1"},
        inputs={"input": "sub task 1"},
        run_id=sub_chain1_id,
        parent_run_id=main_chain_id,
    )
    callback_handler.on_chain_end(
        outputs={"output": "sub result 1"},
        run_id=sub_chain1_id,
        parent_run_id=main_chain_id,
    )

    # Second sub-chain
    callback_handler.on_chain_start(
        serialized={"name": "SubChain2"},
        inputs={"input": "sub task 2"},
        run_id=sub_chain2_id,
        parent_run_id=main_chain_id,
    )
    callback_handler.on_chain_end(
        outputs={"output": "sub result 2"},
        run_id=sub_chain2_id,
        parent_run_id=main_chain_id,
    )

    # End the main chain
    callback_handler.on_chain_end(
        outputs={"result": "final answer"},
        run_id=main_chain_id,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 3

    chain_spans = [s for s in spans if "chain" in s.name]
    assert len(chain_spans) == 3

    chain_names = {span.name for span in chain_spans}
    assert "chain MainChain" in chain_names
    assert "chain SubChain1" in chain_names
    assert "chain SubChain2" in chain_names
