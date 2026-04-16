import pytest
from tests.test_utils import DEFAULT_MODEL, USER_ONLY_PROMPT

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.genai.instruments import (
    GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK,
    _GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK_BUCKETS,
    get_metric_data_points,
)


def test_streaming_chat_records_ttft_metric(
    metric_reader, openai_client, instrument_with_content, vcr
):
    """TTFT metric is recorded for streaming chat completions."""
    with vcr.use_cassette("test_chat_completion_streaming.yaml"):
        response = openai_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=USER_ONLY_PROMPT,
            stream=True,
            stream_options={"include_usage": True},
        )
        for _ in response:
            pass

    data_points = get_metric_data_points(metric_reader, GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK)
    assert len(data_points) == 1, (
        "expected exactly one TTFC data point for streaming"
    )

    data_point = data_points[0]
    assert data_point.sum >= 0
    assert data_point.count == 1
    assert data_point.explicit_bounds == tuple(_GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK_BUCKETS)

    assert GenAIAttributes.GEN_AI_OPERATION_NAME in data_point.attributes
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert GenAIAttributes.GEN_AI_REQUEST_MODEL in data_point.attributes
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        == "gpt-4o-mini"
    )
    assert ServerAttributes.SERVER_ADDRESS in data_point.attributes


@pytest.mark.asyncio()
async def test_async_streaming_chat_records_ttft_metric(
    metric_reader, async_openai_client, instrument_with_content, vcr
):
    """TTFT metric is recorded for async streaming chat completions."""
    with vcr.use_cassette("test_async_chat_completion_streaming.yaml"):
        response = await async_openai_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=USER_ONLY_PROMPT,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for _ in response:
            pass

    data_points = get_metric_data_points(metric_reader, GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK)
    assert len(data_points) == 1, (
        "expected exactly one TTFC data point for async streaming"
    )

    data_point = data_points[0]
    assert data_point.sum >= 0
    assert data_point.count == 1
    assert data_point.explicit_bounds == tuple(_GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK_BUCKETS)


def test_non_streaming_chat_does_not_record_ttft_metric(
    metric_reader, openai_client, instrument_with_content, vcr
):
    """TTFT metric should NOT be recorded for non-streaming requests."""
    with vcr.use_cassette("test_chat_completion_metrics.yaml"):
        openai_client.chat.completions.create(
            messages=USER_ONLY_PROMPT, model=DEFAULT_MODEL, stream=False
        )

    data_points = get_metric_data_points(metric_reader, GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK)
    assert len(data_points) == 0, (
        "gen_ai.client.operation.time_to_first_chunk metric should not be recorded for non-streaming"
    )


def test_streaming_tool_calls_records_ttft_metric(
    metric_reader, openai_client, instrument_with_content, vcr
):
    """TTFT metric is recorded for streaming responses with tool calls."""
    with vcr.use_cassette(
        "test_chat_completion_multiple_tools_streaming_with_content.yaml"
    ):
        response = openai_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": "What's the weather?"}],
            stream=True,
            stream_options={"include_usage": True},
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {"type": "string"},
                            },
                        },
                    },
                }
            ],
        )
        for _ in response:
            pass

    data_points = get_metric_data_points(metric_reader, GEN_AI_CLIENT_OPERATION_TIME_TO_FIRST_CHUNK)
    assert len(data_points) == 1, (
        "expected exactly one TTFC data point for streaming tool calls"
    )

    data_point = data_points[0]
    assert data_point.sum >= 0
    assert data_point.count == 1
