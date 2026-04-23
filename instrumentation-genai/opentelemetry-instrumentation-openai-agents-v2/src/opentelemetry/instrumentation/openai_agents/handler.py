"""OpenTelemetry handler for OpenAI Realtime API Sessions

Translates raw server events from the OpenAI Realtime API into
OpenTelemetry spans and metrics following the GenAI semantic conventions.
Invoked from the ``_emit_event`` patch before listeners are dispatched.

Spans:
  * Session span        -- ``gen_ai.operation.name = invoke_agent``
  * Response span       -- ``gen_ai.operation.name = generate_content``
  * Tool execution span -- ``gen_ai.operation.name = execute_tool``

Metrics (histograms):
  * ``gen_ai.client.token.usage``
  * ``gen_ai.client.operation.duration``
  * ``gen_ai.server.time_to_first_token``
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agents.realtime.model_events import RealtimeModelEvent
from agents.realtime.openai_realtime import get_server_event_type_adapter
from openai.types.realtime import (
    ConversationItemAdded,
    InputAudioBufferSpeechStartedEvent,
    InputAudioBufferSpeechStoppedEvent,
    RealtimeConversationItemFunctionCallOutput,
    RealtimeErrorEvent,
    RealtimeResponseUsage,
    RealtimeSessionCreateRequest,
    ResponseCreatedEvent,
    ResponseDoneEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    SessionCreatedEvent,
)

from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.instrumentation.openai_agents._constants import (
    ERROR_TYPE,
    EXECUTE_TOOL,
    GEN_AI_AGENT_NAME,
    GEN_AI_OPERATION_NAME,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_RESPONSE_ID,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_RESPONSE_STATUS,
    GEN_AI_SESSION_ID,
    GEN_AI_TOKEN_TYPE,
    GEN_AI_TOOL_CALL_ID,
    GEN_AI_TOOL_NAME,
    GEN_AI_TOOL_TYPE,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    GENERATE_CONTENT,
    INVOKE_AGENT,
    METER_NAME,
    METER_VERSION,
    OPERATION_DURATION_METRIC,
    SERVER_ADDRESS,
    SERVER_PORT,
    TIME_TO_FIRST_TOKEN_METRIC,
    TOKEN_USAGE_METRIC,
)
from opentelemetry.trace import Span, SpanKind, StatusCode, get_current_span
from opentelemetry.trace.propagation import set_span_in_context

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_UNKNOWN = "unknown"

class RealtimeEventType:
    """Server event ``type`` strings from the OpenAI Realtime API."""

    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    RESPONSE_CREATED = "response.created"
    RESPONSE_DONE = "response.done"
    FUNCTION_CALL = "response.function_call_arguments.done"
    CONVERSATION_ITEM_ADDED = "conversation.item.added"
    AUDIO_DELTA = "response.output_audio.delta"
    TRANSCRIPT_DELTA = "response.output_audio_transcript.delta"
    TRANSCRIPT_DONE = "response.output_audio_transcript.done"
    TEXT_DELTA = "response.text.delta"
    SPEECH_STARTED = "input_audio_buffer.speech_started"
    SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
    INPUT_TRANSCRIPTION_COMPLETED = "conversation.item.input_audio_transcription.completed"
    INPUT_TRANSCRIPTION_FAILED = "conversation.item.input_audio_transcription.failed"
    ERROR = "error"

class SpanName:
    """Display names used when creating OpenTelemetry spans."""

    SESSION_CREATED = "realtime_session"
    AGENT_RESPONSE = "agent.response"
    FUNCTION_CALL = "execute_tool"
    USER_INPUT = "user.input"


class RealtimeTelemetryHandler:
    def __init__(
        self,
        *,
        server_address: str | None = None,
        server_port: int | None = None,
        provider_name: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        self._server_address = server_address
        self._server_port = server_port
        self.agent_name: str | None = agent_name
        self.provider_name = provider_name or "openai"
        self._root_context: Context = set_span_in_context(get_current_span())
        self._spans: dict[str, Span] = {}
        self._session_id: str | None = None

        self._init_metrics()

        self._model: str | None = None
        self._response_start_times: dict[str, float] = {}
        self._first_token_recorded: set[str] = set()

    def _init_metrics(self): # TODO make this module level pass in meter name and version has constants to avoid initialization on every handler instance creation
        """Initialize metrics instruments."""
        _meter = metrics.get_meter(METER_NAME, METER_VERSION)
        self._token_usage_histogram = _meter.create_histogram(
            TOKEN_USAGE_METRIC,
            description="Number of input and output tokens used",
            unit="{token}",
        )
        self._operation_duration_histogram = _meter.create_histogram(
            OPERATION_DURATION_METRIC,
            description="GenAI operation duration",
            unit="s",
        )
        self._time_to_first_token = _meter.create_histogram(
            TIME_TO_FIRST_TOKEN_METRIC,
            description="Time to generate first token for successful responses",
            unit="s",
        )

    def _context_for(self, key: str | None = None) -> Context:
        """Return context for the first matching span, falling back to session then root."""
        if key is not None:
            if span := self._spans.get(key):
                return set_span_in_context(span)
        if session := self._spans.get("session"):
            return set_span_in_context(session)
        return self._root_context

    def _end_span(self, key: str) -> None:
        span = self._spans.pop(key, None)
        if span is not None:
            try:
                if span.is_recording():
                    span.end()
            except Exception:
                logger.debug("Failed to end span for key %s", key)

    def cleanup(self) -> None:
        for key in list(self._spans):
            self._end_span(key)

    def handle_event(self, event: RealtimeModelEvent) -> Context:
        if event.type != "raw_server_event":
            match event.type:
                case "function_call":
                    return self._context_for(event.call_id)
                case _:
                    return self._context_for()

        try:
            parsed = get_server_event_type_adapter().validate_python(event.data)
        except Exception:
            logger.debug("Failed to parse realtime server event", exc_info=True)
            return self._context_for()

        match parsed.type:
            case RealtimeEventType.SESSION_CREATED:
                return self._handle_session_created(parsed)
            case RealtimeEventType.SPEECH_STARTED:
                return self._handle_speech_started(parsed)
            case RealtimeEventType.RESPONSE_CREATED:
                return self._handle_response_created(parsed)
            case RealtimeEventType.SPEECH_STOPPED:
                return self._handle_speech_stopped(parsed)
            case RealtimeEventType.RESPONSE_DONE:
                return self._handle_response_done(parsed)
            case RealtimeEventType.FUNCTION_CALL:
                return self._handle_function_call_arguments_done(parsed)
            case RealtimeEventType.CONVERSATION_ITEM_ADDED:
                return self._handle_conversation_item_added(parsed)
            case (
                RealtimeEventType.AUDIO_DELTA
                | RealtimeEventType.TRANSCRIPT_DELTA
                | RealtimeEventType.TEXT_DELTA
            ):
                self._maybe_record_ttft(parsed.response_id)
                return self._context_for()

            case RealtimeEventType.ERROR:
                return self._handle_error(parsed)
            case _:
                return self._context_for()

    def _handle_session_created(self, event: SessionCreatedEvent) -> Context:
        span = tracer.start_span(
            SpanName.SESSION_CREATED, context=self._root_context, kind=SpanKind.INTERNAL
        )
        self._spans["session"] = span

        session_id = getattr(event.session, "id", None)
        if session_id:
            self._session_id = session_id
            span.set_attribute(GEN_AI_SESSION_ID, session_id)

        span.set_attribute(GEN_AI_OPERATION_NAME, INVOKE_AGENT)
        span.set_attribute(GEN_AI_PROVIDER_NAME, self.provider_name)
        if self._server_address is not None:
            span.set_attribute(SERVER_ADDRESS, self._server_address)
        if self._server_port is not None:
            span.set_attribute(SERVER_PORT, self._server_port)
        if self.agent_name is not None:
            span.set_attribute(GEN_AI_AGENT_NAME, self.agent_name)

        if isinstance(event.session, RealtimeSessionCreateRequest):
            if event.session.model is not None:
                self._model = event.session.model
                span.set_attribute(GEN_AI_REQUEST_MODEL, self._model)
        return set_span_in_context(span)


    def _handle_speech_started(
        self, event: InputAudioBufferSpeechStartedEvent
    ) -> Context:
        ctx = self._context_for()
        span = tracer.start_span(
            SpanName.USER_INPUT, context=ctx, kind=SpanKind.INTERNAL
        )
        item_id = event.item_id
        self._spans[item_id] = span

        span.set_attribute(GEN_AI_OPERATION_NAME, SpanName.USER_INPUT)
        span.set_attribute(GEN_AI_PROVIDER_NAME, self.provider_name)
        return set_span_in_context(span)

    def _handle_speech_stopped(
        self, event: InputAudioBufferSpeechStoppedEvent
    ) -> Context:
        self._end_span(event.item_id)
        return self._context_for()


    def _handle_response_created(self, event: ResponseCreatedEvent) -> Context:
        ctx = self._context_for()
        span = tracer.start_span(
            SpanName.AGENT_RESPONSE, context=ctx, kind=SpanKind.INTERNAL
        )
        response = event.response
        response_id = response.id or _UNKNOWN
        self._spans[response_id] = span

        span.set_attribute(GEN_AI_OPERATION_NAME, SpanName.AGENT_RESPONSE)
        span.set_attribute(GEN_AI_PROVIDER_NAME, self.provider_name)
        span.set_attribute(GEN_AI_RESPONSE_ID, response_id)
        if self._model:
            span.set_attribute(GEN_AI_REQUEST_MODEL, self._model)

        self._response_start_times[response_id] = time.monotonic()
        return set_span_in_context(span)

    def _handle_response_done(self, event: ResponseDoneEvent) -> Context:
        response = event.response
        response_id = response.id or _UNKNOWN
        span = self._spans.get(response_id)
        
        if span:
            if response.status:
                span.set_attribute(GEN_AI_RESPONSE_STATUS, response.status)
            if self._model:
                span.set_attribute(GEN_AI_RESPONSE_MODEL, self._model)

            if status_details := response.status_details:
                if status_details.reason:
                    span.set_attribute(
                        GEN_AI_RESPONSE_FINISH_REASONS,
                        status_details.reason,
                    )
                if status_details.error:
                    err = status_details.error
                    span.set_status(
                        StatusCode.ERROR,
                        f"{err.type}: {err.code}"
                        if err.code
                        else str(err.type),
                    )
                    span.set_attribute(
                        ERROR_TYPE, err.type or _UNKNOWN
                    )

            if response.status in ("failed", "incomplete") and (
                not response.status_details
                or not response.status_details.error
            ):
                span.set_status(
                    StatusCode.ERROR, f"Response {response.status}"
                )

            if usage := response.usage:
                span.set_attributes(_extract_token_attributes(usage))
                self._record_token_usage_metric(usage)

        # Operation duration metric
        start_time = self._response_start_times.pop(response_id, None)
        self._first_token_recorded.discard(response_id)
        if start_time is not None:
            duration = time.monotonic() - start_time
            attrs: dict[str, str] = {
                GEN_AI_OPERATION_NAME: "realtime_session",
                GEN_AI_PROVIDER_NAME: self.provider_name,
            }
            if self._model:
                attrs[GEN_AI_REQUEST_MODEL] = self._model
            if response.status and response.status in ("failed", "incomplete"):
                attrs[ERROR_TYPE] = response.status
            self._operation_duration_histogram.record(duration, attrs)


        self._end_span(response_id)
        return self._context_for()

    def _handle_function_call_arguments_done(
        self, event: ResponseFunctionCallArgumentsDoneEvent
    ) -> Context:
        ctx = self._context_for(event.response_id)
        function_name = event.name
        call_id = event.call_id

        span = tracer.start_span(
            f"{SpanName.FUNCTION_CALL} {function_name}",
            context=ctx,
            kind=SpanKind.INTERNAL,
        )
        self._spans[call_id] = span

        span.set_attribute(GEN_AI_OPERATION_NAME, EXECUTE_TOOL)
        span.set_attribute(GEN_AI_PROVIDER_NAME, self.provider_name)
        span.set_attribute(GEN_AI_TOOL_CALL_ID, call_id)
        span.set_attribute(GEN_AI_TOOL_NAME, function_name)
        span.set_attribute(GEN_AI_TOOL_TYPE, "function")
        return set_span_in_context(span)

    def _handle_conversation_item_added(
        self, event: ConversationItemAdded
    ) -> Context:
        if isinstance(event.item, RealtimeConversationItemFunctionCallOutput):
            self._end_span(event.item.call_id)
        return self._context_for()


    def _handle_error(self, event: RealtimeErrorEvent) -> Context:
        error = event.error
        logger.error(
            "Realtime API error: [%s] %s (code=%s, event_id=%s)",
            error.type,
            error.message,
            error.code,
            error.event_id,
        )
        span = self._spans.get("session")
        if span:
            span.set_status(StatusCode.ERROR, error.message)
            span.set_attribute(ERROR_TYPE, error.type or _UNKNOWN)
            if error.event_id is not None:
                span.set_attribute("gen_ai.error.event_id", error.event_id)
        return self._context_for()


    def _record_token_usage_metric(self, usage: RealtimeResponseUsage) -> None:
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens

        if input_tokens is None and usage.input_token_details:
            input_tokens = (usage.input_token_details.audio_tokens or 0) + (
                usage.input_token_details.text_tokens or 0
            )
        if output_tokens is None and usage.output_token_details:
            output_tokens = (usage.output_token_details.audio_tokens or 0) + (
                usage.output_token_details.text_tokens or 0
            )

        base_attrs: dict[str, Any] = {
            GEN_AI_OPERATION_NAME: GENERATE_CONTENT,
            GEN_AI_PROVIDER_NAME: self.provider_name,
        }
        if self._server_address is not None:
            base_attrs[SERVER_ADDRESS] = self._server_address
        if self._server_port is not None:
            base_attrs[SERVER_PORT] = self._server_port
        if self._model:
            base_attrs[GEN_AI_REQUEST_MODEL] = self._model
            base_attrs[GEN_AI_RESPONSE_MODEL] = self._model

        if input_tokens is not None:
            self._token_usage_histogram.record(
                input_tokens, {**base_attrs, GEN_AI_TOKEN_TYPE: "input"}
            )
        if output_tokens is not None:
            self._token_usage_histogram.record(
                output_tokens, {**base_attrs, GEN_AI_TOKEN_TYPE: "output"}
            )

    def _maybe_record_ttft(self, response_id: str) -> None:
        """Record time-to-first-token once per response on the first content delta."""
        if response_id in self._first_token_recorded:
            return
        start_time = self._response_start_times.get(response_id)
        if start_time is None:
            return
        self._first_token_recorded.add(response_id)
        ttft = time.monotonic() - start_time
        attrs: dict[str, str] = {
            GEN_AI_OPERATION_NAME: "realtime_session",
            GEN_AI_PROVIDER_NAME: self.provider_name,
        }
        if self._model:
            attrs[GEN_AI_REQUEST_MODEL] = self._model
            attrs[GEN_AI_RESPONSE_MODEL] = self._model
        self._time_to_first_token.record(ttft, attrs)



def _extract_token_attributes(usage: RealtimeResponseUsage) -> dict[str, Any]:
    """Extract token usage attributes for span recording."""
    attrs: dict[str, Any] = {}

    if usage.input_tokens is not None:
        attrs[GEN_AI_USAGE_INPUT_TOKENS] = usage.input_tokens
    elif usage.input_token_details:
        attrs[GEN_AI_USAGE_INPUT_TOKENS] = (
            usage.input_token_details.audio_tokens or 0
        ) + (usage.input_token_details.text_tokens or 0)

    if usage.output_tokens is not None:
        attrs[GEN_AI_USAGE_OUTPUT_TOKENS] = usage.output_tokens
    elif usage.output_token_details:
        attrs[GEN_AI_USAGE_OUTPUT_TOKENS] = (
            usage.output_token_details.audio_tokens or 0
        ) + (usage.output_token_details.text_tokens or 0)

    return attrs
