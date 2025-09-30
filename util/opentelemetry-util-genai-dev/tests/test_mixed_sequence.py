from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    EmbeddingInvocation,
    LLMInvocation,
    ToolCall,
)


def test_mixed_sequence_llm_tool_llm_embedding_parenting():
    handler = get_telemetry_handler()

    # First LLM (kept open while tool call executes)
    llm1 = LLMInvocation(request_model="model-alpha", provider="prov")
    handler.start_llm(llm1)
    assert llm1.span is not None

    # ToolCall inside llm1 span context
    tool = ToolCall(
        name="translate", id="t1", arguments={"text": "hola"}, provider="prov"
    )
    handler.start_tool_call(tool)
    assert tool.span is not None
    # Same trace id indicates proper parenting; span ids must differ
    assert (
        tool.span.get_span_context().trace_id
        == llm1.span.get_span_context().trace_id
    )
    assert (
        tool.span.get_span_context().span_id
        != llm1.span.get_span_context().span_id
    )

    handler.stop_tool_call(tool)
    handler.stop_llm(llm1)

    # Second LLM (separate trace allowed) then embedding under its context
    llm2 = LLMInvocation(request_model="model-beta")
    handler.start_llm(llm2)
    emb = EmbeddingInvocation(request_model="embed-1", input_texts=["abc"])
    handler.start_embedding(emb)
    assert emb.span is not None and llm2.span is not None
    assert (
        emb.span.get_span_context().trace_id
        == llm2.span.get_span_context().trace_id
    )
    handler.stop_embedding(emb)
    handler.stop_llm(llm2)
