# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import inspect
import json

import pytest
from openai import APIConnectionError, BadRequestError, NotFoundError, OpenAI

from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
from opentelemetry.instrumentation.openai_v2.response_wrappers import (
    ResponseStreamWrapper,
)
from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.genai.utils import is_experimental_mode

from .test_utils import (
    DEFAULT_MODEL,
    USER_ONLY_EXPECTED_INPUT_MESSAGES,
    USER_ONLY_PROMPT,
    assert_all_attributes,
    assert_cache_attributes,
    assert_messages_attribute,
    format_simple_expected_output_message,
    get_responses_weather_tool_definition,
)

try:
    # Responses is not available in the oldest supported OpenAI SDK, so keep
    # this import guarded. Pylint runs against the oldest dependency set and
    # cannot resolve this optional module there.
    # pylint: disable-next=no-name-in-module
    from openai.resources.responses.responses import Responses as _Responses

    HAS_RESPONSES_API = True
    _create_params = set(inspect.signature(_Responses.create).parameters)
    _has_tools_param = "tools" in _create_params
    _has_reasoning_param = "reasoning" in _create_params
except ImportError:
    HAS_RESPONSES_API = False
    _has_tools_param = False
    _has_reasoning_param = False


pytestmark = pytest.mark.skipif(
    not HAS_RESPONSES_API, reason="Responses API requires a newer openai SDK"
)

SYSTEM_INSTRUCTIONS = "You are a helpful assistant."
EXPECTED_SYSTEM_INSTRUCTIONS = [
    {
        "type": "text",
        "content": SYSTEM_INSTRUCTIONS,
    }
]
INVALID_MODEL = "this-model-does-not-exist"
REASONING_MODEL = "gpt-5.4"
REASONING_PROMPT = """
Write a bash script that takes a matrix represented as a string with
format '[1,2],[3,4],[5,6]' and prints the transpose in the same format.
"""


def _skip_if_not_latest():
    if not is_experimental_mode():
        pytest.skip(
            "Responses create instrumentation only supports the latest experimental semconv path"
        )


def _load_span_messages(span, attribute):
    value = span.attributes.get(attribute)
    assert value is not None
    return json.loads(value)


def _assert_response_content(span, response, log_exporter):
    assert_messages_attribute(
        span.attributes[GenAIAttributes.GEN_AI_INPUT_MESSAGES],
        USER_ONLY_EXPECTED_INPUT_MESSAGES,
    )
    assert (
        json.loads(span.attributes[GenAIAttributes.GEN_AI_SYSTEM_INSTRUCTIONS])
        == EXPECTED_SYSTEM_INSTRUCTIONS
    )
    assert_messages_attribute(
        span.attributes[GenAIAttributes.GEN_AI_OUTPUT_MESSAGES],
        format_simple_expected_output_message(response.output_text),
    )
    assert len(log_exporter.get_finished_logs()) == 0


def _assert_request_attrs(
    span,
    *,
    temperature=None,
    top_p=None,
    max_tokens=None,
    output_type=None,
):
    if temperature is not None:
        assert (
            span.attributes[GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE]
            == temperature
        )
    if top_p is not None:
        assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_TOP_P] == top_p
    if max_tokens is not None:
        assert (
            span.attributes[GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS]
            == max_tokens
        )
    if output_type is not None:
        assert (
            span.attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] == output_type
        )


def _collect_completed_response(stream):
    response = None
    for event in stream:
        if event.type == "response.completed":
            response = event.response
    assert response is not None
    return response


def test_responses_uninstrument_removes_patching(
    span_exporter, tracer_provider, logger_provider, meter_provider
):
    instrumentor = OpenAIInstrumentor()
    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    instrumentor.uninstrument()

    assert len(span_exporter.get_finished_spans()) == 0


def test_responses_multiple_instrument_uninstrument_cycles(
    tracer_provider, logger_provider, meter_provider
):
    instrumentor = OpenAIInstrumentor()

    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    instrumentor.uninstrument()

    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    instrumentor.uninstrument()

    instrumentor.instrument(
        tracer_provider=tracer_provider,
        logger_provider=logger_provider,
        meter_provider=meter_provider,
    )
    instrumentor.uninstrument()


@pytest.mark.vcr()
def test_responses_create_basic(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    response = openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=False,
    )

    (span,) = span_exporter.get_finished_spans()
    assert_all_attributes(
        span,
        DEFAULT_MODEL,
        True,
        response.id,
        response.model,
        response.usage.input_tokens,
        response.usage.output_tokens,
        response_service_tier=getattr(response, "service_tier", None),
    )
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == (
        "stop",
    )
    assert GenAIAttributes.GEN_AI_INPUT_MESSAGES not in span.attributes
    assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES not in span.attributes


@pytest.mark.vcr()
def test_responses_create_captures_content(
    request,
    span_exporter,
    log_exporter,
    openai_client,
    instrument_with_content,
):
    _skip_if_not_latest()

    response = openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=False,
        text={"format": {"type": "text"}},
    )

    (span,) = span_exporter.get_finished_spans()
    assert_all_attributes(
        span,
        DEFAULT_MODEL,
        True,
        response.id,
        response.model,
        response.usage.input_tokens,
        response.usage.output_tokens,
        response_service_tier=getattr(response, "service_tier", None),
    )
    _assert_response_content(span, response, log_exporter)


@pytest.mark.vcr()
def test_responses_create_with_all_params(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    response = openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        max_output_tokens=50,
        temperature=0.7,
        top_p=0.9,
        service_tier="default",
        text={"format": {"type": "text"}},
    )

    (span,) = span_exporter.get_finished_spans()
    assert_all_attributes(
        span,
        DEFAULT_MODEL,
        True,
        response.id,
        response.model,
        response.usage.input_tokens,
        response.usage.output_tokens,
        request_service_tier="default",
        response_service_tier=getattr(response, "service_tier", None),
    )
    _assert_request_attrs(
        span,
        temperature=0.7,
        top_p=0.9,
        max_tokens=50,
        output_type="text",
    )


@pytest.mark.vcr()
def test_responses_create_token_usage(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    response = openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input="Count to 5.",
    )

    (span,) = span_exporter.get_finished_spans()
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        == response.usage.input_tokens
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == response.usage.output_tokens
    )


@pytest.mark.vcr()
def test_responses_create_aggregates_cache_tokens(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    response = openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
    )

    (span,) = span_exporter.get_finished_spans()
    assert_cache_attributes(span, response.usage)


@pytest.mark.vcr()
def test_responses_create_stop_reason(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input="Say hi.",
    )

    (span,) = span_exporter.get_finished_spans()
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == (
        "stop",
    )


def test_responses_create_connection_error(
    span_exporter, instrument_no_content
):
    _skip_if_not_latest()

    client = OpenAI(base_url="http://localhost:4242")

    with pytest.raises(APIConnectionError):
        client.responses.create(  # pylint: disable=no-member
            model=DEFAULT_MODEL,
            input="Hello",
            timeout=0.1,
        )

    (span,) = span_exporter.get_finished_spans()
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == DEFAULT_MODEL
    )
    assert span.attributes[ServerAttributes.SERVER_ADDRESS] == "localhost"
    assert span.attributes[ServerAttributes.SERVER_PORT] == 4242
    assert span.attributes[ErrorAttributes.ERROR_TYPE] == "APIConnectionError"


@pytest.mark.vcr()
def test_responses_create_api_error(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    with pytest.raises((BadRequestError, NotFoundError)) as exc_info:
        openai_client.responses.create(
            model=INVALID_MODEL,
            input="Hello",
        )

    (span,) = span_exporter.get_finished_spans()
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == INVALID_MODEL
    )
    assert (
        span.attributes[ErrorAttributes.ERROR_TYPE]
        == type(exc_info.value).__name__
    )


@pytest.mark.vcr()
def test_responses_create_streaming(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    with openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        service_tier="default",
        stream=True,
    ) as stream:
        response = _collect_completed_response(stream)

    (span,) = span_exporter.get_finished_spans()
    assert_all_attributes(
        span,
        DEFAULT_MODEL,
        True,
        response.id,
        response.model,
        response.usage.input_tokens,
        response.usage.output_tokens,
        request_service_tier="default",
        response_service_tier=getattr(response, "service_tier", None),
    )


@pytest.mark.vcr()
def test_responses_create_streaming_aggregates_cache_tokens(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    with openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=True,
    ) as stream:
        response = _collect_completed_response(stream)

    (span,) = span_exporter.get_finished_spans()
    assert_cache_attributes(span, response.usage)


@pytest.mark.vcr()
def test_responses_create_streaming_captures_content(
    request,
    span_exporter,
    log_exporter,
    openai_client,
    instrument_with_content,
):
    _skip_if_not_latest()

    with openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=True,
    ) as stream:
        response = _collect_completed_response(stream)

    (span,) = span_exporter.get_finished_spans()
    assert_all_attributes(
        span,
        DEFAULT_MODEL,
        True,
        response.id,
        response.model,
        response.usage.input_tokens,
        response.usage.output_tokens,
        response_service_tier=getattr(response, "service_tier", None),
    )
    _assert_response_content(span, response, log_exporter)


@pytest.mark.vcr()
def test_responses_create_streaming_iteration(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    stream = openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input="Say hi.",
        stream=True,
    )
    events = list(stream)

    assert len(events) > 0

    (span,) = span_exporter.get_finished_spans()
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == DEFAULT_MODEL
    )
    assert GenAIAttributes.GEN_AI_RESPONSE_ID in span.attributes
    assert GenAIAttributes.GEN_AI_RESPONSE_MODEL in span.attributes
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == (
        "stop",
    )
    assert GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS in span.attributes
    assert GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS in span.attributes


@pytest.mark.vcr()
def test_responses_create_streaming_delegates_response_attribute(
    request, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    stream = openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input="Say hi.",
        stream=True,
    )

    assert stream.response is not None
    assert stream.response.status_code == 200
    assert stream.response.headers.get("x-request-id") is not None
    stream.close()


def test_responses_create_streaming_connection_error(
    span_exporter, instrument_no_content
):
    _skip_if_not_latest()

    client = OpenAI(base_url="http://localhost:4242")

    with pytest.raises(APIConnectionError):
        client.responses.create(  # pylint: disable=no-member
            model=DEFAULT_MODEL,
            input="Hello",
            stream=True,
            timeout=0.1,
        )

    (span,) = span_exporter.get_finished_spans()
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == DEFAULT_MODEL
    )
    assert span.attributes[ErrorAttributes.ERROR_TYPE] == "APIConnectionError"


@pytest.mark.vcr()
def test_responses_stream_wrapper_finalize_idempotent(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    stream = openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=True,
    )

    response = _collect_completed_response(stream)
    stream.close()

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert_all_attributes(
        spans[0],
        DEFAULT_MODEL,
        True,
        response.id,
        response.model,
        response.usage.input_tokens,
        response.usage.output_tokens,
        response_service_tier=getattr(response, "service_tier", None),
    )


@pytest.mark.vcr()
def test_responses_create_stream_propagation_error(
    request, span_exporter, openai_client, instrument_no_content, monkeypatch
):
    _skip_if_not_latest()

    stream = openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=True,
    )

    class ErrorInjectingStreamDelegate:
        def __init__(self, inner):
            self._inner = inner
            self._count = 0

        def __iter__(self):
            return self

        def __next__(self):
            if self._count == 1:
                raise ConnectionError("connection reset during stream")
            self._count += 1
            return next(self._inner)

        def close(self):
            return self._inner.close()

        def __getattr__(self, name):
            return getattr(self._inner, name)

    monkeypatch.setattr(
        stream, "stream", ErrorInjectingStreamDelegate(stream.stream)
    )

    with pytest.raises(
        ConnectionError, match="connection reset during stream"
    ):
        with stream:
            for _ in stream:
                pass

    (span,) = span_exporter.get_finished_spans()
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == DEFAULT_MODEL
    )
    assert span.attributes[ErrorAttributes.ERROR_TYPE] == "ConnectionError"


@pytest.mark.vcr()
def test_responses_create_streaming_user_exception(
    request, span_exporter, openai_client, instrument_no_content
):
    _skip_if_not_latest()

    with pytest.raises(ValueError, match="User raised exception"):
        with openai_client.responses.create(
            model=DEFAULT_MODEL,
            instructions=SYSTEM_INSTRUCTIONS,
            input=USER_ONLY_PROMPT[0]["content"],
            stream=True,
        ) as stream:
            for _ in stream:
                raise ValueError("User raised exception")

    (span,) = span_exporter.get_finished_spans()
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == DEFAULT_MODEL
    )
    assert span.attributes[ErrorAttributes.ERROR_TYPE] == "ValueError"


@pytest.mark.vcr()
def test_responses_create_instrumentation_error_swallowed(
    request, span_exporter, openai_client, instrument_no_content, monkeypatch
):
    _skip_if_not_latest()

    def exploding_process_event(self, event):
        del self
        del event
        raise RuntimeError("instrumentation bug")

    monkeypatch.setattr(
        ResponseStreamWrapper, "process_event", exploding_process_event
    )

    with openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=True,
    ) as stream:
        events = list(stream)

    assert len(events) > 0

    (span,) = span_exporter.get_finished_spans()
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == DEFAULT_MODEL
    )
    assert ErrorAttributes.ERROR_TYPE not in span.attributes


@pytest.mark.vcr()
@pytest.mark.skipif(
    not _has_tools_param,
    reason="openai SDK too old to support 'tools' parameter on Responses.create",
)
def test_responses_create_captures_tool_call_content(
    request, span_exporter, openai_client, instrument_with_content
):
    _skip_if_not_latest()

    openai_client.responses.create(
        model=DEFAULT_MODEL,
        input="What's the weather in Seattle right now?",
        tools=[get_responses_weather_tool_definition()],
        tool_choice={"type": "function", "name": "get_current_weather"},
    )

    (span,) = span_exporter.get_finished_spans()
    assert (
        span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == DEFAULT_MODEL
    )
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == (
        "tool_calls",
    )

    input_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_INPUT_MESSAGES
    )
    assert input_messages[0]["role"] == "user"

    output_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_OUTPUT_MESSAGES
    )
    tool_call_parts = [
        part
        for message in output_messages
        for part in message.get("parts", [])
        if part.get("type") == "tool_call"
    ]
    assert len(tool_call_parts) > 0
    assert tool_call_parts[0]["name"] == "get_current_weather"
    assert "arguments" in tool_call_parts[0]


@pytest.mark.vcr()
@pytest.mark.skipif(
    not _has_reasoning_param,
    reason=(
        "openai SDK too old to support 'reasoning' parameter on Responses.create"
    ),
)
def test_responses_create_reports_reasoning_tokens(
    request, span_exporter, openai_client, instrument_with_content
):
    _skip_if_not_latest()

    response = openai_client.responses.create(
        model=REASONING_MODEL,
        reasoning={"effort": "low"},
        input=[
            {
                "role": "user",
                "content": REASONING_PROMPT,
            }
        ],
        max_output_tokens=300,
        timeout=30.0,
    )

    reasoning_tokens = getattr(
        getattr(response.usage, "output_tokens_details", None),
        "reasoning_tokens",
        None,
    )

    assert reasoning_tokens is not None
    assert reasoning_tokens > 0

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    (span,) = spans
    assert span.attributes[GenAIAttributes.GEN_AI_REQUEST_MODEL] == (
        REASONING_MODEL
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS]
        == response.usage.input_tokens
    )
    assert (
        span.attributes[GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS]
        == response.usage.output_tokens
    )
    assert span.attributes[GenAIAttributes.GEN_AI_RESPONSE_FINISH_REASONS] == (
        "stop",
    )

    output_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_OUTPUT_MESSAGES
    )
    assert len(output_messages) > 0


@pytest.mark.vcr()
def test_responses_create_with_content_span_unsampled(
    request,
    span_exporter,
    log_exporter,
    openai_client,
    instrument_with_content_unsampled,
):
    _skip_if_not_latest()

    openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=False,
    )

    assert len(span_exporter.get_finished_spans()) == 0
    assert len(log_exporter.get_finished_logs()) == 0


@pytest.mark.vcr()
def test_responses_create_with_content_shapes(
    request,
    span_exporter,
    log_exporter,
    openai_client,
    instrument_with_content,
):
    _skip_if_not_latest()

    openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=False,
    )

    (span,) = span_exporter.get_finished_spans()
    input_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_INPUT_MESSAGES
    )
    output_messages = _load_span_messages(
        span, GenAIAttributes.GEN_AI_OUTPUT_MESSAGES
    )

    assert input_messages[0]["role"] == "user"
    assert input_messages[0]["parts"][0]["type"] == "text"
    assert output_messages[0]["role"] == "assistant"
    assert output_messages[0]["parts"][0]["type"] == "text"
    assert len(log_exporter.get_finished_logs()) == 0


@pytest.mark.vcr()
def test_responses_create_event_only_no_content_in_span(
    request, span_exporter, log_exporter, openai_client, instrument_event_only
):
    _skip_if_not_latest()

    openai_client.responses.create(
        model=DEFAULT_MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=USER_ONLY_PROMPT[0]["content"],
        stream=False,
    )

    (span,) = span_exporter.get_finished_spans()
    assert GenAIAttributes.GEN_AI_INPUT_MESSAGES not in span.attributes
    assert GenAIAttributes.GEN_AI_OUTPUT_MESSAGES not in span.attributes
    assert GenAIAttributes.GEN_AI_SYSTEM_INSTRUCTIONS not in span.attributes

    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    assert (
        logs[0].log_record.event_name
        == "gen_ai.client.inference.operation.details"
    )
