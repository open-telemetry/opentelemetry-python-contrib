import json
from typing import Optional

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes


# span_exporter, start_instrumentation, chat_openai_gpt_3_5_turbo_model are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
def test_chat_openai_gpt_3_5_turbo_model_llm_call(
    span_exporter, start_instrumentation, chat_openai_gpt_3_5_turbo_model
):
    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    response = chat_openai_gpt_3_5_turbo_model.invoke(messages)
    assert response.content == "The capital of France is Paris."

    # verify spans
    spans = span_exporter.get_finished_spans()
    print(f"spans: {spans}")
    for span in spans:
        print(f"span: {span}")
        print(f"span attributes: {span.attributes}")
    assert_openai_completion_attributes(spans[0], response)


# span_exporter, start_instrumentation, us_amazon_nova_lite_v1_0 are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
def test_us_amazon_nova_lite_v1_0_bedrock_llm_call(
    span_exporter, start_instrumentation, us_amazon_nova_lite_v1_0
):
    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = us_amazon_nova_lite_v1_0.invoke(messages)

    assert result.content.find("The capital of France is Paris") != -1

    # verify spans
    spans = span_exporter.get_finished_spans()
    print(f"spans: {spans}")
    for span in spans:
        print(f"span: {span}")
        print(f"span attributes: {span.attributes}")
    # TODO: fix the code and ensure the assertions are correct
    assert_bedrock_completion_attributes(spans[0], result)


# span_exporter, start_instrumentation, gemini are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
def test_gemini(span_exporter, start_instrumentation, gemini):
    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = gemini.invoke(messages)

    assert result.content.find("The capital of France is **Paris**") != -1

    # verify spans
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 0  # No spans should be created for gemini as of now


def assert_openai_completion_attributes(
    span: ReadableSpan, response: Optional
):
    assert span.name.startswith("chat ")
    assert span.attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME] == "chat"
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL] in {
        "gpt-3.5-turbo",
        "gpt-3.5-turbo-0125",
    }
    assert span.attributes[
        gen_ai_attributes.GEN_AI_RESPONSE_MODEL
    ] == response.response_metadata.get("model_name")
    assert span.attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME] == "chat"
    if gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS in span.attributes:
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
        )
    if gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE in span.attributes:
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE]
            == 0.1
        )
    assert span.attributes["gen_ai.provider.name"] == "openai"
    assert gen_ai_attributes.GEN_AI_RESPONSE_ID in span.attributes
    if gen_ai_attributes.GEN_AI_REQUEST_TOP_P in span.attributes:
        assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TOP_P] == 0.9
    if gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY in span.attributes:
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY]
            == 0.5
        )
    if gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY in span.attributes:
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY]
            == 0.5
        )
    stop_sequences_raw = span.attributes.get(
        gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES
    )
    if stop_sequences_raw:
        if isinstance(stop_sequences_raw, str):
            stop_sequences = json.loads(stop_sequences_raw)
        else:
            stop_sequences = stop_sequences_raw
        assert all(seq in ["\n", "Human:", "AI:"] for seq in stop_sequences)
    if gen_ai_attributes.GEN_AI_REQUEST_SEED in span.attributes:
        assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_SEED] == 100

    input_tokens = response.response_metadata.get("token_usage").get(
        "prompt_tokens"
    )
    if input_tokens:
        assert (
            input_tokens
            == span.attributes[gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS]
        )
    else:
        assert (
            gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes
        )

    output_tokens = response.response_metadata.get("token_usage").get(
        "completion_tokens"
    )
    if output_tokens:
        assert (
            output_tokens
            == span.attributes[gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )
    else:
        assert (
            gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
        )


def assert_bedrock_completion_attributes(
    span: ReadableSpan, response: Optional
):
    assert span.name == "chat us.amazon.nova-lite-v1:0"
    assert span.attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME] == "chat"
    assert (
        span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL]
        == "us.amazon.nova-lite-v1:0"
    )

    assert span.attributes["gen_ai.provider.name"] == "amazon_bedrock"
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
    assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE] == 0.1

    input_tokens = response.usage_metadata.get("input_tokens")
    if input_tokens:
        assert (
            input_tokens
            == span.attributes[gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS]
        )
    else:
        assert (
            gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes
        )

    output_tokens = response.usage_metadata.get("output_tokens")
    if output_tokens:
        assert (
            output_tokens
            == span.attributes[gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        )
    else:
        assert (
            gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
        )
