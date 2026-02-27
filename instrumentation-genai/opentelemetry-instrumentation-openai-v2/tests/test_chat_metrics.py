import pytest

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    openai_attributes as OpenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics

_DURATION_BUCKETS = (
    0.01,
    0.02,
    0.04,
    0.08,
    0.16,
    0.32,
    0.64,
    1.28,
    2.56,
    5.12,
    10.24,
    20.48,
    40.96,
    81.92,
)
_TOKEN_USAGE_BUCKETS = (
    1,
    4,
    16,
    64,
    256,
    1024,
    4096,
    16384,
    65536,
    262144,
    1048576,
    4194304,
    16777216,
    67108864,
)


def assert_all_metric_attributes(data_point):
    assert GenAIAttributes.GEN_AI_OPERATION_NAME in data_point.attributes
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_OPERATION_NAME]
        == GenAIAttributes.GenAiOperationNameValues.CHAT.value
    )
    assert GenAIAttributes.GEN_AI_SYSTEM in data_point.attributes
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_SYSTEM]
        == GenAIAttributes.GenAiSystemValues.OPENAI.value
    )
    assert GenAIAttributes.GEN_AI_REQUEST_MODEL in data_point.attributes
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL]
        == "gpt-4o-mini"
    )
    assert GenAIAttributes.GEN_AI_RESPONSE_MODEL in data_point.attributes
    assert (
        data_point.attributes[GenAIAttributes.GEN_AI_RESPONSE_MODEL]
        == "gpt-4o-mini-2024-07-18"
    )
    assert (
        OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER in data_point.attributes
    )
    assert (
        data_point.attributes[OpenAIAttributes.OPENAI_RESPONSE_SERVICE_TIER]
        == "default"
    )
    assert (
        data_point.attributes[ServerAttributes.SERVER_ADDRESS]
        == "api.openai.com"
    )


@pytest.mark.vcr()
def test_chat_completion_metrics(
    metric_reader, openai_client, instrument_with_content
):
    llm_model_value = "gpt-4o-mini"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    openai_client.chat.completions.create(
        messages=messages_value, model=llm_model_value, stream=False
    )

    metrics = metric_reader.get_metrics_data().resource_metrics
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics
    assert len(metric_data) == 2

    duration_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
        ),
        None,
    )
    assert duration_metric is not None

    duration_point = duration_metric.data.data_points[0]
    assert duration_point.sum > 0
    assert_all_metric_attributes(duration_point)
    assert duration_point.explicit_bounds == _DURATION_BUCKETS

    token_usage_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
        ),
        None,
    )
    assert token_usage_metric is not None

    input_token_usage = next(
        (
            d
            for d in token_usage_metric.data.data_points
            if d.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
            == GenAIAttributes.GenAiTokenTypeValues.INPUT.value
        ),
        None,
    )
    assert input_token_usage is not None
    assert input_token_usage.sum == 12

    assert input_token_usage.explicit_bounds == _TOKEN_USAGE_BUCKETS
    assert input_token_usage.bucket_counts[2] == 1
    assert_all_metric_attributes(input_token_usage)

    output_token_usage = next(
        (
            d
            for d in token_usage_metric.data.data_points
            if d.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
            == GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value
        ),
        None,
    )
    assert output_token_usage is not None
    assert output_token_usage.sum == 5
    # assert against buckets [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536, 262144, 1048576, 4194304, 16777216, 67108864]
    assert output_token_usage.bucket_counts[2] == 1
    assert_all_metric_attributes(output_token_usage)


@pytest.mark.vcr()
@pytest.mark.asyncio()
async def test_async_chat_completion_metrics(
    metric_reader, async_openai_client, instrument_with_content
):
    llm_model_value = "gpt-4o-mini"
    messages_value = [{"role": "user", "content": "Say this is a test"}]

    await async_openai_client.chat.completions.create(
        messages=messages_value, model=llm_model_value, stream=False
    )

    metrics = metric_reader.get_metrics_data().resource_metrics
    assert len(metrics) == 1

    metric_data = metrics[0].scope_metrics[0].metrics
    assert len(metric_data) == 2

    duration_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_OPERATION_DURATION
        ),
        None,
    )
    assert duration_metric is not None
    assert duration_metric.data.data_points[0].sum > 0
    assert_all_metric_attributes(duration_metric.data.data_points[0])

    token_usage_metric = next(
        (
            m
            for m in metric_data
            if m.name == gen_ai_metrics.GEN_AI_CLIENT_TOKEN_USAGE
        ),
        None,
    )
    assert token_usage_metric is not None

    input_token_usage = next(
        (
            d
            for d in token_usage_metric.data.data_points
            if d.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
            == GenAIAttributes.GenAiTokenTypeValues.INPUT.value
        ),
        None,
    )

    assert input_token_usage is not None
    assert input_token_usage.sum == 12
    assert_all_metric_attributes(input_token_usage)

    output_token_usage = next(
        (
            d
            for d in token_usage_metric.data.data_points
            if d.attributes[GenAIAttributes.GEN_AI_TOKEN_TYPE]
            == GenAIAttributes.GenAiTokenTypeValues.COMPLETION.value
        ),
        None,
    )

    assert output_token_usage is not None
    assert output_token_usage.sum == 12
    assert_all_metric_attributes(output_token_usage)
