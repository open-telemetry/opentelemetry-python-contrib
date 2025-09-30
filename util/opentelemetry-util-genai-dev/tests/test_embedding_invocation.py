from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import EmbeddingInvocation


def test_embedding_invocation_creates_span():
    handler = get_telemetry_handler()
    emb = EmbeddingInvocation(
        request_model="embedding-model",
        input_texts=["a"],
        provider="emb-provider",
    )
    handler.start_embedding(emb)
    assert emb.span is not None
    # ensure stop works without error
    handler.stop_embedding(emb)
    # span should have ended (recording possibly false depending on SDK impl)
    # we at least assert the object reference still exists
    assert emb.span is not None
