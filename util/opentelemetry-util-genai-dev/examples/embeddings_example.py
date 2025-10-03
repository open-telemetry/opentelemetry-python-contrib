#!/usr/bin/env python3
"""
Example demonstrating OpenTelemetry GenAI telemetry for embedding operations.

This example shows:
1. Basic embedding invocation lifecycle
2. Embedding with multiple input texts (batch)
3. Embedding with custom attributes
4. Error handling for embedding operations
5. Embedding with agent context
6. Metrics and span emission for embeddings
"""

import time

from opentelemetry import _logs as logs
from opentelemetry import trace
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    ConsoleLogExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import EmbeddingInvocation, Error


def setup_telemetry():
    """Set up OpenTelemetry providers for tracing, metrics, and logging."""
    # Set up tracing
    trace_provider = TracerProvider()
    trace_provider.add_span_processor(
        SimpleSpanProcessor(ConsoleSpanExporter())
    )
    trace.set_tracer_provider(trace_provider)

    # Set up metrics
    metric_reader = PeriodicExportingMetricReader(
        ConsoleMetricExporter(), export_interval_millis=5000
    )
    meter_provider = MeterProvider(metric_readers=[metric_reader])

    # Set up logging (for events)
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(
        SimpleLogRecordProcessor(ConsoleLogExporter())
    )
    logs.set_logger_provider(logger_provider)

    return trace_provider, meter_provider, logger_provider


def example_basic_embedding():
    """Example 1: Basic embedding invocation with a single text."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Embedding Invocation")
    print("=" * 60)

    handler = get_telemetry_handler()

    # Create embedding invocation
    embedding = EmbeddingInvocation(
        operation_name="embedding",
        request_model="text-embedding-3-small",
        input_texts=["Hello, world!"],
        provider="openai",
    )

    # Start the embedding operation
    handler.start_embedding(embedding)
    time.sleep(0.05)  # Simulate API call

    # Simulate response - populate dimension count and tokens
    embedding.dimension_count = 1536
    embedding.input_tokens = 3

    # Finish the embedding operation
    handler.stop_embedding(embedding)

    print(f"✓ Completed embedding for 1 text")
    print(f"  Model: {embedding.request_model}")
    print(f"  Dimensions: {embedding.dimension_count}")
    print(f"  Input tokens: {embedding.input_tokens}")


def example_batch_embedding():
    """Example 2: Batch embedding with multiple input texts."""
    print("\n" + "=" * 60)
    print("Example 2: Batch Embedding")
    print("=" * 60)

    handler = get_telemetry_handler()

    # Create batch embedding invocation
    texts = [
        "The quick brown fox jumps over the lazy dog",
        "Machine learning is transforming technology",
        "OpenTelemetry provides observability for applications",
    ]

    embedding = EmbeddingInvocation(
        operation_name="embedding",
        request_model="text-embedding-ada-002",
        input_texts=texts,
        provider="openai",
        encoding_formats=["float"],
    )

    # Start the embedding operation
    handler.start_embedding(embedding)
    time.sleep(0.1)  # Simulate API call

    # Simulate response
    embedding.dimension_count = 1536
    embedding.input_tokens = 25

    # Finish the embedding operation
    handler.stop_embedding(embedding)

    print(f"✓ Completed batch embedding for {len(texts)} texts")
    print(f"  Model: {embedding.request_model}")
    print(f"  Dimensions: {embedding.dimension_count}")
    print(f"  Input tokens: {embedding.input_tokens}")
    print(f"  Encoding formats: {embedding.encoding_formats}")


def example_embedding_with_server_info():
    """Example 3: Embedding with server address and port."""
    print("\n" + "=" * 60)
    print("Example 3: Embedding with Server Information")
    print("=" * 60)

    handler = get_telemetry_handler()

    # Create embedding with server details
    embedding = EmbeddingInvocation(
        operation_name="embedding",
        request_model="all-MiniLM-L6-v2",
        input_texts=["Semantic search query"],
        provider="huggingface",
        server_address="api.huggingface.co",
        server_port=443,
    )

    # Start the embedding operation
    handler.start_embedding(embedding)
    time.sleep(0.08)  # Simulate API call

    # Simulate response
    embedding.dimension_count = 384
    embedding.input_tokens = 4

    # Finish the embedding operation
    handler.stop_embedding(embedding)

    print(f"✓ Completed embedding with server info")
    print(f"  Model: {embedding.request_model}")
    print(f"  Server: {embedding.server_address}:{embedding.server_port}")
    print(f"  Dimensions: {embedding.dimension_count}")


def example_embedding_with_custom_attributes():
    """Example 4: Embedding with custom attributes."""
    print("\n" + "=" * 60)
    print("Example 4: Embedding with Custom Attributes")
    print("=" * 60)

    handler = get_telemetry_handler()

    # Create embedding with custom attributes
    embedding = EmbeddingInvocation(
        operation_name="embedding",
        request_model="text-embedding-3-large",
        input_texts=["Document for vector database"],
        provider="openai",
        attributes={
            "use_case": "vector_search",
            "collection": "documents",
            "user_id": "user-123",
        },
    )

    # Start the embedding operation
    handler.start_embedding(embedding)
    time.sleep(0.06)  # Simulate API call

    # Simulate response
    embedding.dimension_count = 3072
    embedding.input_tokens = 5

    # Finish the embedding operation
    handler.stop_embedding(embedding)

    print(f"✓ Completed embedding with custom attributes")
    print(f"  Model: {embedding.request_model}")
    print(f"  Custom attributes: {embedding.attributes}")


def example_embedding_with_agent_context():
    """Example 5: Embedding within an agent context."""
    print("\n" + "=" * 60)
    print("Example 5: Embedding with Agent Context")
    print("=" * 60)

    handler = get_telemetry_handler()

    # Create embedding with agent context
    embedding = EmbeddingInvocation(
        operation_name="embedding",
        request_model="text-embedding-3-small",
        input_texts=["Query from agent workflow"],
        provider="openai",
        agent_name="retrieval_agent",
        agent_id="agent-456",
    )

    # Start the embedding operation
    handler.start_embedding(embedding)
    time.sleep(0.05)  # Simulate API call

    # Simulate response
    embedding.dimension_count = 1536
    embedding.input_tokens = 5

    # Finish the embedding operation
    handler.stop_embedding(embedding)

    print(f"✓ Completed embedding with agent context")
    print(f"  Agent: {embedding.agent_name} (ID: {embedding.agent_id})")
    print(f"  Model: {embedding.request_model}")


def example_embedding_error():
    """Example 6: Handling embedding errors."""
    print("\n" + "=" * 60)
    print("Example 6: Embedding Error Handling")
    print("=" * 60)

    handler = get_telemetry_handler()

    # Create embedding invocation
    embedding = EmbeddingInvocation(
        operation_name="embedding",
        request_model="text-embedding-3-small",
        input_texts=["This will fail"],
        provider="openai",
    )

    # Start the embedding operation
    handler.start_embedding(embedding)
    time.sleep(0.03)  # Simulate API call

    # Simulate an error
    error = Error(
        message="Rate limit exceeded",
        type=Exception,
    )
    embedding.error_type = "RateLimitError"

    # Fail the embedding operation
    handler.fail_embedding(embedding, error)

    print(f"✗ Embedding failed with error")
    print(f"  Error: {error.message}")
    print(f"  Error type: {embedding.error_type}")


def example_multiple_embeddings():
    """Example 7: Multiple sequential embeddings."""
    print("\n" + "=" * 60)
    print("Example 7: Multiple Sequential Embeddings")
    print("=" * 60)

    handler = get_telemetry_handler()

    documents = [
        "First document for embedding",
        "Second document for embedding",
        "Third document for embedding",
    ]

    for idx, doc in enumerate(documents, 1):
        embedding = EmbeddingInvocation(
            operation_name="embedding",
            request_model="text-embedding-3-small",
            input_texts=[doc],
            provider="openai",
            attributes={"document_index": idx},
        )

        handler.start_embedding(embedding)
        time.sleep(0.04)  # Simulate API call

        # Simulate response
        embedding.dimension_count = 1536
        embedding.input_tokens = 5

        handler.stop_embedding(embedding)
        print(f"  ✓ Completed embedding {idx}/{len(documents)}")

    print(f"✓ Completed all {len(documents)} embeddings")


def main():
    """Run all embedding examples."""
    print("\n" + "=" * 60)
    print("OpenTelemetry GenAI Embeddings Examples")
    print("=" * 60)

    # Set up telemetry
    trace_provider, meter_provider, logger_provider = setup_telemetry()

    # Run examples
    example_basic_embedding()
    example_batch_embedding()
    example_embedding_with_server_info()
    example_embedding_with_custom_attributes()
    example_embedding_with_agent_context()
    example_embedding_error()
    example_multiple_embeddings()

    # Force flush to ensure all telemetry is exported
    print("\n" + "=" * 60)
    print("Flushing telemetry data...")
    print("=" * 60)
    trace_provider.force_flush()
    meter_provider.force_flush()
    logger_provider.force_flush()

    print("\n✓ All examples completed successfully!")
    print("Check the console output above for spans, metrics, and events.\n")


if __name__ == "__main__":
    main()