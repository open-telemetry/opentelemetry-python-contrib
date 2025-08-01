from typing import Optional

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes


# span_exporter, chatOpenAI_client, start_instrumentation are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
def test_langchain_call(
    span_exporter, chatOpenAI_client, start_instrumentation
):
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.1,
        max_tokens=100,
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.5,
        stop_sequences=["\n", "Human:", "AI:"],
        seed=100,
    )

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    response = llm.invoke(messages)
    assert response.content == "The capital of France is Paris."

    # verify spans
    spans = span_exporter.get_finished_spans()
    print(f"spans: {spans}")
    for span in spans:
        print(f"span: {span}")
        print(f"span attributes: {span.attributes}")
    assert_openai_completion_attributes(spans[0], response)

def assert_openai_completion_attributes(
    span: ReadableSpan,
    response: Optional
):
    assert span.name == "ChatOpenAI.chat"
    assert span.attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME] == "chat"
    assert span.attributes[gen_ai_attributes.GEN_AI_SYSTEM] == "ChatOpenAI"
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL] == "gpt-3.5-turbo"
    assert span.attributes[gen_ai_attributes.GEN_AI_RESPONSE_MODEL] == "gpt-3.5-turbo-0125"
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE] == 0.1
    # TODO: add to semantic conventions
    assert span.attributes["gen_ai.provider.name"] == "openai"
    assert gen_ai_attributes.GEN_AI_RESPONSE_ID in span.attributes
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TOP_P] == 0.9
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY] == 0.5
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY] == 0.5
    stop_sequences = span.attributes.get(gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES)
    assert all(seq in ["\n", "Human:", "AI:"] for seq in stop_sequences)
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_SEED] == 100

    input_tokens = response.response_metadata.get("token_usage").get("prompt_tokens")
    if input_tokens:
        assert input_tokens == span.attributes[gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS]
    else:
        assert gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes

    output_tokens = response.response_metadata.get("token_usage").get("completion_tokens")
    if output_tokens:
        assert output_tokens == span.attributes[gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    else:
        assert gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes



