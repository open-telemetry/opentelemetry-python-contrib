import json

import pytest

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


@pytest.mark.vcr()
def test_chat_completion(exporter, openai_client):
    llm_model_value = "gpt-4"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    kwargs = {
        "model": llm_model_value,
        "messages": messages_value,
        "stream": False,
    }

    response = openai_client.chat.completions.create(**kwargs)
    spans = exporter.get_finished_spans()
    chat_completion_span = spans[0]
    # assert that the span name is correct
    assert chat_completion_span.name == f"chat {llm_model_value}"

    attributes = chat_completion_span.attributes
    operation_name = attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    system = attributes[GenAIAttributes.GEN_AI_SYSTEM]
    request_model = attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    response_model = attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
    response_id = attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
    input_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    # assert that the attributes are correct
    assert (
        operation_name == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert system == GenAIAttributes.GenAiSystemValues.OPENAI.value
    assert request_model == llm_model_value
    assert response_model == response.model
    assert response_id == response.id
    assert input_tokens == response.usage.prompt_tokens
    assert output_tokens == response.usage.completion_tokens

    events = chat_completion_span.events

    # assert that the prompt and completion events are present
    prompt_event = list(
        filter(
            lambda event: event.name == "gen_ai.content.prompt",
            events,
        )
    )
    completion_event = list(
        filter(
            lambda event: event.name == "gen_ai.content.completion",
            events,
        )
    )

    assert prompt_event
    assert completion_event

    # assert that the prompt and completion events have the correct attributes
    assert prompt_event[0].attributes[
        GenAIAttributes.GEN_AI_PROMPT
    ] == json.dumps(messages_value)

    assert (
        json.loads(
            completion_event[0].attributes[GenAIAttributes.GEN_AI_COMPLETION]
        )[0]["content"]
        == response.choices[0].message.content
    )


@pytest.mark.vcr()
def test_chat_completion_streaming(exporter, openai_client):
    llm_model_value = "gpt-4"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    kwargs = {
        "model": llm_model_value,
        "messages": messages_value,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    response_stream_usage = None
    response_stream_model = None
    response_stream_id = None
    response_stream_result = ""
    response = openai_client.chat.completions.create(**kwargs)
    for chunk in response:
        if chunk.choices:
            response_stream_result += chunk.choices[0].delta.content or ""

        # get the last chunk
        if getattr(chunk, "usage", None):
            response_stream_usage = chunk.usage
            response_stream_model = chunk.model
            response_stream_id = chunk.id

    spans = exporter.get_finished_spans()
    streaming_span = spans[0]

    assert streaming_span.name == f"chat {llm_model_value}"
    attributes = streaming_span.attributes

    operation_name = attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
    system = attributes[GenAIAttributes.GEN_AI_SYSTEM]
    request_model = attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
    response_model = attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
    response_id = attributes[GenAIAttributes.GEN_AI_RESPONSE_ID]
    input_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
    output_tokens = attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
    assert (
        operation_name == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert system == GenAIAttributes.GenAiSystemValues.OPENAI.value
    assert request_model == llm_model_value
    assert response_model == response_stream_model
    assert response_id == response_stream_id
    assert input_tokens == response_stream_usage.prompt_tokens
    assert output_tokens == response_stream_usage.completion_tokens

    events = streaming_span.events

    # assert that the prompt and completion events are present
    prompt_event = list(
        filter(
            lambda event: event.name == "gen_ai.content.prompt",
            events,
        )
    )
    completion_event = list(
        filter(
            lambda event: event.name == "gen_ai.content.completion",
            events,
        )
    )

    assert prompt_event
    assert completion_event

    # assert that the prompt and completion events have the correct attributes
    assert prompt_event[0].attributes[
        GenAIAttributes.GEN_AI_PROMPT
    ] == json.dumps(messages_value)

    assert (
        json.loads(
            completion_event[0].attributes[GenAIAttributes.GEN_AI_COMPLETION]
        )[0]["content"]
        == response_stream_result
    )
