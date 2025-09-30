from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    EmbeddingInvocation,
    Error,
    LLMInvocation,
)


def test_generic_lifecycle_llm():
    handler = get_telemetry_handler()
    inv = LLMInvocation(request_model="model-1")
    # Start, finish, and fail should not raise
    handler.start(inv)
    inv.output_messages = []  # no-op messages
    handler.finish(inv)
    handler.fail(inv, Error(message="err", type=ValueError))
    # Span should exist
    assert inv.span is not None


def test_generic_lifecycle_embedding():
    handler = get_telemetry_handler()
    emb = EmbeddingInvocation(request_model="emb-model", input_texts=["a"])
    handler.start(emb)
    handler.finish(emb)
    handler.fail(emb, Error(message="error", type=RuntimeError))
    assert emb.span is not None


def test_generic_lifecycle_unknown():
    handler = get_telemetry_handler()

    class X:
        pass

    x = X()
    # Generic methods should return the same object for unknown types
    assert handler.start(x) is x
    assert handler.finish(x) is x
    assert handler.fail(x, Error(message="msg", type=Exception)) is x
