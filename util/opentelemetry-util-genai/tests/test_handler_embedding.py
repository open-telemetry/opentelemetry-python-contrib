from __future__ import annotations

from unittest import TestCase

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.trace import SpanKind
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    EmbeddingInvocation,
    Error,
)


class TestEmbeddingHandler(TestCase):
    def setUp(self) -> None:
        self.span_exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider()
        self.tracer_provider.add_span_processor(
            SimpleSpanProcessor(self.span_exporter)
        )

    def _make_handler(self) -> TelemetryHandler:
        return TelemetryHandler(
            tracer_provider=self.tracer_provider,
        )

    def test_start_stop_creates_span(self) -> None:
        handler = self._make_handler()
        invocation = EmbeddingInvocation(
            request_model="text-embedding-3-small",
            provider="openai",
        )
        handler.start(invocation)
        handler.stop(invocation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(span.name, "embeddings text-embedding-3-small")
        self.assertEqual(
            span.attributes[GenAI.GEN_AI_OPERATION_NAME], "embeddings"
        )
        self.assertEqual(span.attributes[GenAI.GEN_AI_PROVIDER_NAME], "openai")

    def test_span_kind_client(self) -> None:
        handler = self._make_handler()
        invocation = EmbeddingInvocation(provider="openai")
        handler.start(invocation)
        handler.stop(invocation)

        spans = self.span_exporter.get_finished_spans()
        self.assertEqual(spans[0].kind, SpanKind.CLIENT)

    def test_all_attributes(self) -> None:
        handler = self._make_handler()
        invocation = EmbeddingInvocation(
            request_model="text-embedding-3-small",
            provider="openai",
            server_address="api.openai.com",
            server_port=443,
            encoding_formats=["float"],
            dimension_count=1536,
        )
        handler.start(invocation)
        invocation.response_model_name = "text-embedding-3-small"
        invocation.input_tokens = 24
        handler.stop(invocation)

        attrs = self.span_exporter.get_finished_spans()[0].attributes
        self.assertEqual(
            attrs[GenAI.GEN_AI_REQUEST_MODEL], "text-embedding-3-small"
        )
        self.assertEqual(
            attrs[GenAI.GEN_AI_RESPONSE_MODEL], "text-embedding-3-small"
        )
        self.assertEqual(attrs[GenAI.GEN_AI_USAGE_INPUT_TOKENS], 24)
        self.assertEqual(attrs[GenAI.GEN_AI_EMBEDDINGS_DIMENSION_COUNT], 1536)
        self.assertEqual(
            tuple(attrs[GenAI.GEN_AI_REQUEST_ENCODING_FORMATS]), ("float",)
        )

    def test_fail_sets_error_status(self) -> None:
        handler = self._make_handler()
        invocation = EmbeddingInvocation(provider="openai")
        handler.start(invocation)
        handler.fail(
            invocation, Error(message="embedding failed", type=RuntimeError)
        )

        span = self.span_exporter.get_finished_spans()[0]
        self.assertEqual(span.status.description, "embedding failed")
        self.assertEqual(span.attributes.get("error.type"), "RuntimeError")

    def test_context_manager_success(self) -> None:
        handler = self._make_handler()
        invocation = EmbeddingInvocation(
            request_model="text-embedding-3-small",
            provider="openai",
        )
        with handler.embedding(invocation) as inv:
            inv.input_tokens = 10

        self.assertEqual(
            self.span_exporter.get_finished_spans()[0].name,
            "embeddings text-embedding-3-small",
        )

    def test_context_manager_error(self) -> None:
        handler = self._make_handler()
        with self.assertRaises(ValueError):
            with handler.embedding(EmbeddingInvocation(provider="openai")):
                raise ValueError("test error")

        self.assertEqual(
            self.span_exporter.get_finished_spans()[0].attributes.get(
                "error.type"
            ),
            "ValueError",
        )

    def test_context_manager_default_invocation(self) -> None:
        handler = self._make_handler()
        with handler.embedding() as inv:
            inv.request_model = "text-embedding-3-small"
            inv.provider = "openai"
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 1)

    def test_stop_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        invocation = EmbeddingInvocation()
        result = handler.stop(invocation)
        self.assertIs(result, invocation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)

    def test_fail_without_start_is_noop(self) -> None:
        handler = self._make_handler()
        invocation = EmbeddingInvocation()
        result = handler.fail(
            invocation, Error(message="boom", type=RuntimeError)
        )
        self.assertIs(result, invocation)
        self.assertEqual(len(self.span_exporter.get_finished_spans()), 0)


class TestEmbeddingInvocationType(TestCase):
    def test_defaults(self) -> None:
        inv = EmbeddingInvocation()
        self.assertEqual(inv.operation_name, "embeddings")
        self.assertIsNone(inv.request_model)
        self.assertIsNone(inv.provider)
        self.assertIsNone(inv.encoding_formats)
        self.assertIsNone(inv.dimension_count)
        self.assertIsNone(inv.input_tokens)
        self.assertIsNone(inv.response_model_name)

    def test_custom_attributes(self) -> None:
        inv = EmbeddingInvocation(
            attributes={"custom.key": "custom_value"},
        )
        self.assertEqual(inv.attributes["custom.key"], "custom_value")
