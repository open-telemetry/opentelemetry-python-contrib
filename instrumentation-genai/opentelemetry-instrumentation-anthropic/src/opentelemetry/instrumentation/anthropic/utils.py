# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utility functions for Anthropic instrumentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator, Optional, Sequence
from urllib.parse import urlparse

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import Error, LLMInvocation
from opentelemetry.util.types import AttributeValue

if TYPE_CHECKING:
    from anthropic._streaming import Stream
    from anthropic.lib.streaming import (
        MessageStream,
        MessageStreamManager,
    )
    from anthropic.resources.messages import Messages
    from anthropic.types import Message, RawMessageStreamEvent


@dataclass
class MessageRequestParams:
    """Parameters extracted from Anthropic Messages API calls."""

    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    stop_sequences: Sequence[str] | None = None


_GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)
_GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"


def _normalize_finish_reason(stop_reason: str | None) -> str | None:
    """Map Anthropic stop reasons to GenAI semantic convention values."""
    if stop_reason is None:
        return None

    normalized = {
        "end_turn": "stop",
        "stop_sequence": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
    }.get(stop_reason)
    return normalized or stop_reason


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _extract_usage_tokens(
    usage: Any | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Extract Anthropic usage fields and compute semconv input tokens.

    Returns `(total_input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens)`.
    """
    if usage is None:
        return None, None, None, None

    input_tokens = _as_int(getattr(usage, "input_tokens", None))
    cache_creation_input_tokens = _as_int(
        getattr(usage, "cache_creation_input_tokens", None)
    )
    cache_read_input_tokens = _as_int(
        getattr(usage, "cache_read_input_tokens", None)
    )
    output_tokens = _as_int(getattr(usage, "output_tokens", None))

    if (
        input_tokens is None
        and cache_creation_input_tokens is None
        and cache_read_input_tokens is None
    ):
        total_input_tokens = None
    else:
        total_input_tokens = (
            (input_tokens or 0)
            + (cache_creation_input_tokens or 0)
            + (cache_read_input_tokens or 0)
        )

    return (
        total_input_tokens,
        output_tokens,
        cache_creation_input_tokens,
        cache_read_input_tokens,
    )


# Use parameter signature from
# https://github.com/anthropics/anthropic-sdk-python/blob/9b5ab24ba17bcd5e762e5a5fd69bb3c17b100aaa/src/anthropic/resources/messages/messages.py#L896
# https://github.com/anthropics/anthropic-sdk-python/blob/9b5ab24ba17bcd5e762e5a5fd69bb3c17b100aaa/src/anthropic/resources/messages/messages.py#L963
# to handle named vs positional args robustly
def extract_params(  # pylint: disable=too-many-locals
    *,
    max_tokens: int | None = None,
    messages: Any | None = None,
    model: str | None = None,
    metadata: Any | None = None,
    service_tier: Any | None = None,
    stop_sequences: Sequence[str] | None = None,
    stream: Any | None = None,
    system: Any | None = None,
    temperature: float | None = None,
    thinking: Any | None = None,
    tool_choice: Any | None = None,
    tools: Any | None = None,
    top_k: int | None = None,
    top_p: float | None = None,
    extra_headers: Any | None = None,
    extra_query: Any | None = None,
    extra_body: Any | None = None,
    timeout: Any | None = None,
    **_kwargs: Any,
) -> MessageRequestParams:
    """Extract relevant parameters from Anthropic Messages API arguments."""
    return MessageRequestParams(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        stop_sequences=stop_sequences,
    )


def set_server_address_and_port(
    client_instance: "Messages", attributes: dict[str, Any]
) -> None:
    """Extract server address and port from the Anthropic client instance."""
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return

    port: Optional[int] = None
    if hasattr(base_url, "host"):
        # httpx.URL object
        attributes[ServerAttributes.SERVER_ADDRESS] = base_url.host
        port = getattr(base_url, "port", None)
    elif isinstance(base_url, str):
        url = urlparse(base_url)
        attributes[ServerAttributes.SERVER_ADDRESS] = url.hostname
        port = url.port

    if port and port != 443 and port > 0:
        attributes[ServerAttributes.SERVER_PORT] = port


def get_llm_request_attributes(
    params: MessageRequestParams, client_instance: "Messages"
) -> dict[str, AttributeValue]:
    """Extract LLM request attributes from MessageRequestParams.

    Returns a dictionary of OpenTelemetry semantic convention attributes for LLM requests.
    The attributes follow the GenAI semantic conventions (gen_ai.*) and server semantic
    conventions (server.*) as defined in the OpenTelemetry specification.

    GenAI attributes included:
    - gen_ai.operation.name: The operation name (e.g., "chat")
    - gen_ai.system: The GenAI system identifier (e.g., "anthropic")
    - gen_ai.request.model: The model identifier
    - gen_ai.request.max_tokens: Maximum tokens in the request
    - gen_ai.request.temperature: Sampling temperature
    - gen_ai.request.top_p: Top-p sampling parameter
    - gen_ai.request.top_k: Top-k sampling parameter
    - gen_ai.request.stop_sequences: Stop sequences for the request

    Server attributes included (if available):
    - server.address: The server hostname
    - server.port: The server port (if not default 443)

    Only non-None values are included in the returned dictionary.
    """
    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: GenAIAttributes.GenAiOperationNameValues.CHAT.value,
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.ANTHROPIC.value,  # pyright: ignore[reportDeprecated]
        GenAIAttributes.GEN_AI_REQUEST_MODEL: params.model,
        GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS: params.max_tokens,
        GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE: params.temperature,
        GenAIAttributes.GEN_AI_REQUEST_TOP_P: params.top_p,
        GenAIAttributes.GEN_AI_REQUEST_TOP_K: params.top_k,
        GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES: params.stop_sequences,
    }

    set_server_address_and_port(client_instance, attributes)

    # Filter out None values
    return {k: v for k, v in attributes.items() if v is not None}


class MessageWrapper:
    """Wrapper for non-streaming Message response that handles telemetry.

    This wrapper extracts telemetry data from the response and finalizes
    the span immediately since the response is complete.
    """

    def __init__(
        self,
        message: "Message",
        handler: TelemetryHandler,
        invocation: LLMInvocation,
    ):
        self._message = message
        self._extract_and_finalize(handler, invocation)

    def _extract_and_finalize(
        self, handler: TelemetryHandler, invocation: LLMInvocation
    ) -> None:
        """Extract response data and finalize the span."""
        if self._message.model:
            invocation.response_model_name = self._message.model

        if self._message.id:
            invocation.response_id = self._message.id

        finish_reason = _normalize_finish_reason(self._message.stop_reason)
        if finish_reason:
            invocation.finish_reasons = [finish_reason]

        if self._message.usage:
            (
                input_tokens,
                output_tokens,
                cache_creation_input_tokens,
                cache_read_input_tokens,
            ) = _extract_usage_tokens(self._message.usage)
            invocation.input_tokens = input_tokens
            invocation.output_tokens = output_tokens
            if cache_creation_input_tokens is not None:
                invocation.attributes[
                    _GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS
                ] = cache_creation_input_tokens
            if cache_read_input_tokens is not None:
                invocation.attributes[
                    _GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS
                ] = cache_read_input_tokens

        handler.stop_llm(invocation)

    @property
    def message(self) -> "Message":
        """Return the wrapped Message object."""
        return self._message


class StreamWrapper(Iterator["RawMessageStreamEvent"]):
    """Wrapper for Anthropic Stream that handles telemetry.

    This wrapper wraps Stream[RawMessageStreamEvent] returned by
    Messages.create(stream=True). It processes streaming chunks,
    extracts telemetry data, and ensures the span is properly ended
    when the stream is consumed.
    """

    def __init__(
        self,
        stream: "Stream[RawMessageStreamEvent]",
        handler: TelemetryHandler,
        invocation: LLMInvocation,
    ):
        self._stream = stream
        self._handler = handler
        self._invocation = invocation
        self._response_id: Optional[str] = None
        self._response_model: Optional[str] = None
        self._stop_reason: Optional[str] = None
        self._input_tokens: Optional[int] = None
        self._output_tokens: Optional[int] = None
        self._cache_creation_input_tokens: Optional[int] = None
        self._cache_read_input_tokens: Optional[int] = None
        self._finalized = False

    def _update_usage(self, usage: Any | None) -> None:
        (
            input_tokens,
            output_tokens,
            cache_creation_input_tokens,
            cache_read_input_tokens,
        ) = _extract_usage_tokens(usage)
        if input_tokens is not None:
            self._input_tokens = input_tokens
        if output_tokens is not None:
            self._output_tokens = output_tokens
        if cache_creation_input_tokens is not None:
            self._cache_creation_input_tokens = cache_creation_input_tokens
        if cache_read_input_tokens is not None:
            self._cache_read_input_tokens = cache_read_input_tokens

    def _process_chunk(self, chunk: "RawMessageStreamEvent") -> None:
        """Extract telemetry data from a streaming chunk."""
        # Handle message_start event - contains initial message info
        if chunk.type == "message_start":
            message = getattr(chunk, "message", None)
            if message:
                if hasattr(message, "id") and message.id:
                    self._response_id = message.id
                if hasattr(message, "model") and message.model:
                    self._response_model = message.model
                # message_start also contains initial usage with input_tokens
                if hasattr(message, "usage") and message.usage:
                    self._update_usage(message.usage)

        # Handle message_delta event - contains stop_reason and output token usage
        elif chunk.type == "message_delta":
            delta = getattr(chunk, "delta", None)
            if delta and hasattr(delta, "stop_reason") and delta.stop_reason:
                self._stop_reason = _normalize_finish_reason(delta.stop_reason)
            # message_delta contains usage with output_tokens (and may repeat input_tokens)
            usage = getattr(chunk, "usage", None)
            self._update_usage(usage)

    def _finalize_invocation(self) -> None:
        """Update invocation with collected data and stop the span."""
        if self._finalized:
            return

        if self._response_model:
            self._invocation.response_model_name = self._response_model
        if self._response_id:
            self._invocation.response_id = self._response_id
        if self._stop_reason:
            self._invocation.finish_reasons = [self._stop_reason]
        if self._input_tokens is not None:
            self._invocation.input_tokens = self._input_tokens
        if self._output_tokens is not None:
            self._invocation.output_tokens = self._output_tokens
        if self._cache_creation_input_tokens is not None:
            self._invocation.attributes[
                _GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS
            ] = self._cache_creation_input_tokens
        if self._cache_read_input_tokens is not None:
            self._invocation.attributes[
                _GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS
            ] = self._cache_read_input_tokens

        self._handler.stop_llm(self._invocation)
        self._finalized = True

    def __iter__(self) -> "StreamWrapper":
        return self

    def __next__(self) -> "RawMessageStreamEvent":
        try:
            chunk = next(self._stream)
            self._process_chunk(chunk)
            return chunk
        except StopIteration:
            self._finalize_invocation()
            raise
        except Exception as exc:
            self._handler.fail_llm(
                self._invocation, Error(message=str(exc), type=type(exc))
            )
            raise

    def __enter__(self) -> "StreamWrapper":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.close()
        return False

    def close(self) -> None:
        """Close the underlying stream and finalize telemetry."""
        if hasattr(self._stream, "close"):
            self._stream.close()
        self._finalize_invocation()


class MessageStreamManagerWrapper:
    """Wrapper for MessageStreamManager that handles telemetry.

    This wrapper wraps the MessageStreamManager context manager returned by
    Messages.stream(). It extracts telemetry data from the final message
    when the context exits.
    """

    def __init__(
        self,
        stream_manager: "MessageStreamManager",
        handler: TelemetryHandler,
        invocation: LLMInvocation,
    ):
        self._stream_manager = stream_manager
        self._handler = handler
        self._invocation = invocation
        self._message_stream: Optional["MessageStream"] = None

    def __enter__(self) -> "MessageStream":
        """Enter the context and return the underlying MessageStream."""
        try:
            self._message_stream = self._stream_manager.__enter__()
            return self._message_stream
        except Exception as exc:
            # Handle errors during context entry (e.g., connection errors)
            self._handler.fail_llm(
                self._invocation,
                Error(message=str(exc), type=type(exc)),
            )
            raise

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Exit the context, extract telemetry, and finalize the span."""
        # Extract telemetry from the final message before exiting
        if self._message_stream is not None and exc_type is None:
            self._extract_telemetry_from_stream()
            self._handler.stop_llm(self._invocation)
        elif exc_type is not None:
            # Handle error case
            self._handler.fail_llm(
                self._invocation,
                Error(
                    message=str(exc_val) if exc_val else str(exc_type),
                    type=exc_type,
                ),
            )
        # Always exit the underlying stream manager
        return self._stream_manager.__exit__(exc_type, exc_val, exc_tb)  # type: ignore[return-value]

    def _extract_telemetry_from_stream(self) -> None:
        """Extract telemetry data from the MessageStream's final message."""
        if self._message_stream is None:
            return

        try:
            # get_final_message() returns the accumulated Message object
            final_message = self._message_stream.get_final_message()

            if final_message.model:
                self._invocation.response_model_name = final_message.model

            if final_message.id:
                self._invocation.response_id = final_message.id

            finish_reason = _normalize_finish_reason(final_message.stop_reason)
            if finish_reason:
                self._invocation.finish_reasons = [finish_reason]

            if final_message.usage:
                (
                    input_tokens,
                    output_tokens,
                    cache_creation_input_tokens,
                    cache_read_input_tokens,
                ) = _extract_usage_tokens(final_message.usage)
                self._invocation.input_tokens = input_tokens
                self._invocation.output_tokens = output_tokens
                if cache_creation_input_tokens is not None:
                    self._invocation.attributes[
                        _GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS
                    ] = cache_creation_input_tokens
                if cache_read_input_tokens is not None:
                    self._invocation.attributes[
                        _GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS
                    ] = cache_read_input_tokens
        except Exception:  # pylint: disable=broad-exception-caught
            # If we can't get the final message, we still want to end the span
            pass
