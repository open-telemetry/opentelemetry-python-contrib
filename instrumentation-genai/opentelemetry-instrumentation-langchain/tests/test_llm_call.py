from typing import Optional

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from openai import AuthenticationError

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes
from opentelemetry.semconv.attributes import error_attributes


# span_exporter, start_instrumentation, chat_openai_gpt_3_5_turbo_model are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
@pytest.mark.parametrize("capture_content", ["SPAN_ONLY", "NO_CONTENT"])
def test_chat_openai_gpt_3_5_turbo_model_llm_call(
    span_exporter,
    start_instrumentation,
    chat_openai_gpt_3_5_turbo_model,
    monkeypatch,
    capture_content,
):
    monkeypatch.setenv(
        "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", capture_content
    )

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

    verifyContent: bool = True if capture_content == "SPAN_ONLY" else False
    assert_openai_completion_attributes(
        spans[0] if len(spans) > 0 else None,
        response,
        verifyContent=verifyContent,
    )


# span_exporter, start_instrumentation, chat_openai_gpt_3_5_turbo_model are coming from fixtures defined in conftest.py
@pytest.mark.vcr()
@pytest.mark.parametrize("capture_content", ["SPAN_ONLY", "NO_CONTENT"])
def test_chat_openai_gpt_3_5_turbo_model_llm_call_with_error(
    span_exporter,
    start_instrumentation,
    chat_openai_gpt_3_5_turbo_model,
    monkeypatch,
    capture_content,
):
    monkeypatch.setenv(
        "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
    )
    monkeypatch.setenv(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", capture_content
    )

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    response = None
    try:
        response = chat_openai_gpt_3_5_turbo_model.invoke(messages)
    except Exception as e:
        # For this test, to get error, cassettes were recorded with no OPENAI_API_KEY, so an error is expected here.
        assert isinstance(e, AuthenticationError)

    assert response is None

    # verify spans
    spans = span_exporter.get_finished_spans()
    print(f"spans: {spans}")
    for span in spans:
        print(f"span: {span}")
        print(f"span attributes: {span.attributes}")

    verifyContent: bool = True if capture_content == "SPAN_ONLY" else False
    assert_openai_completion_attributes_with_error(
        spans[0] if len(spans) > 0 else None, verifyContent=verifyContent
    )


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
    span: ReadableSpan, response: Optional, verifyContent: bool = True
):
    if span:
        assert span.name == "chat gpt-3.5-turbo"
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME] == "chat"
        )
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL]
            == "gpt-3.5-turbo"
        )
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_RESPONSE_MODEL]
            == "gpt-3.5-turbo-0125"
        )
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
        )
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE]
            == 0.1
        )
        assert span.attributes["gen_ai.provider.name"] == "openai"
        assert gen_ai_attributes.GEN_AI_RESPONSE_ID in span.attributes
        assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TOP_P] == 0.9
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY]
            == 0.5
        )
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY]
            == 0.5
        )
        stop_sequences = span.attributes.get(
            gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES
        )
        assert all(seq in ["\n", "Human:", "AI:"] for seq in stop_sequences)
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
                gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS
                not in span.attributes
            )

        output_tokens = response.response_metadata.get("token_usage").get(
            "completion_tokens"
        )
        if output_tokens:
            assert (
                output_tokens
                == span.attributes[
                    gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS
                ]
            )
        else:
            assert (
                gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS
                not in span.attributes
            )

        if verifyContent:
            input_message = span.attributes[
                gen_ai_attributes.GEN_AI_INPUT_MESSAGES
            ]
            assert input_message is not None
            assert '"role":"system"' in input_message
            assert '"content":"You are a helpful assistant!"' in input_message
            assert '"role":"human"' in input_message
            assert (
                '"content":"What is the capital of France?"' in input_message
            )

            # Assert output message
            output_message = span.attributes[
                gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES
            ]
            assert output_message is not None
            assert '"role":"ai"' in output_message
            assert (
                '"content":"The capital of France is Paris."' in output_message
            )
            assert '"finish_reason":"stop"' in output_message


def assert_openai_completion_attributes_with_error(
    span: ReadableSpan, verifyContent: bool = True
):
    if span is not None:
        assert span.name == "chat gpt-3.5-turbo"
        assert (
            span.attributes[error_attributes.ERROR_TYPE]
            == "AuthenticationError"
        )
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_OPERATION_NAME] == "chat"
        )
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MODEL]
            == "gpt-3.5-turbo"
        )
        assert gen_ai_attributes.GEN_AI_RESPONSE_MODEL not in span.attributes
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS] == 100
        )
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE]
            == 0.1
        )
        assert span.attributes["gen_ai.provider.name"] == "openai"
        assert gen_ai_attributes.GEN_AI_RESPONSE_ID not in span.attributes
        assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_TOP_P] == 0.9
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY]
            == 0.5
        )
        assert (
            span.attributes[gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY]
            == 0.5
        )
        stop_sequences = span.attributes.get(
            gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES
        )
        assert all(seq in ["\n", "Human:", "AI:"] for seq in stop_sequences)
        assert span.attributes[gen_ai_attributes.GEN_AI_REQUEST_SEED] == 100

        assert (
            gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS not in span.attributes
        )

        assert (
            gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS not in span.attributes
        )

        if verifyContent:
            input_message = span.attributes[
                gen_ai_attributes.GEN_AI_INPUT_MESSAGES
            ]
            assert input_message is not None
            assert '"role":"system"' in input_message
            assert '"content":"You are a helpful assistant!"' in input_message
            assert '"role":"human"' in input_message
            assert (
                '"content":"What is the capital of France?"' in input_message
            )

            # Assert output message
            assert (
                gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES not in span.attributes
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
