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

import logging
from typing import TYPE_CHECKING, Any

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

if TYPE_CHECKING:
    from opentelemetry.util.genai.handler import TelemetryHandler
    from opentelemetry.util.genai.types import LLMInvocation

from .utils import (
    get_llm_request_attributes,
    is_streaming,
)

_logger = logging.getLogger(__name__)

OPENAI = GenAIAttributes.GenAiSystemValues.OPENAI.value


# ---------------------------------------------------------------------------
# Content capture helpers
# ---------------------------------------------------------------------------


def _should_capture_content() -> bool:
    """Return True when content conversion should be performed.

    Mirrors the Anthropic instrumentation pattern: only extract content when
    experimental mode is active and a content-capturing mode is set.
    """
    from opentelemetry.util.genai.utils import (  # pylint: disable=import-outside-toplevel
        ContentCapturingMode,
        get_content_capturing_mode,
        is_experimental_mode,
        should_emit_event,
    )

    if not is_experimental_mode():
        return False
    mode = get_content_capturing_mode()
    if mode == ContentCapturingMode.NO_CONTENT:
        return False
    if mode == ContentCapturingMode.EVENT_ONLY and not should_emit_event():
        return False
    return True


def _extract_system_instruction(kwargs: dict):
    """Extract system instruction from the ``instructions`` parameter."""
    from opentelemetry.util.genai.types import (  # pylint: disable=import-outside-toplevel
        Text,
    )

    instructions = kwargs.get("instructions")
    if instructions is None:
        return []
    if isinstance(instructions, str):
        return [Text(content=instructions)]
    return []


def _extract_input_messages(kwargs: dict):
    """Extract input messages from Responses API kwargs.

    The Responses API ``input`` parameter can be:
    - A string (simple text input)
    - A list of message items (with role and content)
    """
    from opentelemetry.util.genai.types import (  # pylint: disable=import-outside-toplevel
        InputMessage,
        Text,
    )

    raw_input = kwargs.get("input")
    if raw_input is None:
        return []

    if isinstance(raw_input, str):
        return [InputMessage(role="user", parts=[Text(content=raw_input)])]

    messages = []
    if isinstance(raw_input, list):
        for item in raw_input:
            role = getattr(item, "role", None) or (
                item.get("role") if isinstance(item, dict) else None
            )
            if not role:
                continue
            content = getattr(item, "content", None) or (
                item.get("content") if isinstance(item, dict) else None
            )
            if isinstance(content, str):
                messages.append(
                    InputMessage(role=role, parts=[Text(content=content)])
                )
            elif isinstance(content, list):
                parts = []
                for part in content:
                    text = getattr(part, "text", None) or (
                        part.get("text") if isinstance(part, dict) else None
                    )
                    if text:
                        parts.append(Text(content=text))
                if parts:
                    messages.append(InputMessage(role=role, parts=parts))
    return messages


def _extract_output_messages(result: Any):
    """Extract output messages from a Responses API result.

    The response ``output`` field is a list of output items. Items with
    type ``"message"`` contain content blocks (output_text, refusal, etc.).
    """
    from opentelemetry.util.genai.types import (  # pylint: disable=import-outside-toplevel
        OutputMessage,
        Text,
    )

    if result is None:
        return []

    output_items = getattr(result, "output", None)
    if not output_items:
        return []

    messages = []
    for item in output_items:
        item_type = getattr(item, "type", None)
        if item_type != "message":
            continue

        role = getattr(item, "role", "assistant")
        status = getattr(item, "status", None)
        finish_reason = "stop" if status == "completed" else (status or "stop")

        content_blocks = getattr(item, "content", [])
        parts = []
        for block in content_blocks:
            block_type = getattr(block, "type", None)
            if block_type == "output_text":
                text = getattr(block, "text", None)
                if text:
                    parts.append(Text(content=text))
            elif block_type == "refusal":
                refusal = getattr(block, "refusal", None)
                if refusal:
                    parts.append(Text(content=refusal))

        messages.append(
            OutputMessage(role=role, parts=parts, finish_reason=finish_reason)
        )

    return messages


# ---------------------------------------------------------------------------
# Patch functions
# ---------------------------------------------------------------------------


def responses_create(
    handler: "TelemetryHandler",
    capture_content: bool,
):
    """Wrap the `create` method of the `Responses` class to trace it."""
    # https://github.com/openai/openai-python/blob/dc68b90655912886bd7a6c7787f96005452ebfc9/src/openai/resources/responses/responses.py#L828

    def traced_method(wrapped, instance, args, kwargs):
        from opentelemetry.util.genai.types import (  # pylint: disable=import-outside-toplevel
            Error,
            LLMInvocation,
        )

        operation_name = (
            GenAIAttributes.GenAiOperationNameValues.CHAT.value
        )
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            operation_name,
        )
        request_model = str(
            span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
            or "unknown"
        )
        streaming = is_streaming(kwargs)

        capture_content = _should_capture_content()
        invocation = handler.start_llm(
            LLMInvocation(
                request_model=request_model,
                operation_name=operation_name,
                provider=OPENAI,
                input_messages=_extract_input_messages(kwargs)
                if capture_content
                else [],
                system_instruction=_extract_system_instruction(kwargs)
                if capture_content
                else [],
                attributes=span_attributes.copy(),
                metric_attributes={
                    GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name
                },
            )
        )

        try:
            result = wrapped(*args, **kwargs)
            if hasattr(result, "parse"):
                parsed_result = result.parse()
            else:
                parsed_result = result

            if streaming:
                return ResponseStreamWrapper(
                    parsed_result,
                    handler,
                    invocation,
                    capture_content,
                )

            _set_invocation_response_attributes(
                invocation, parsed_result, capture_content
            )
            handler.stop_llm(invocation)
            return result

        except Exception as error:
            handler.fail_llm(
                invocation, Error(message=str(error), type=type(error))
            )
            raise

    return traced_method


def responses_retrieve(
    handler: "TelemetryHandler",
    capture_content: bool,
):
    """Wrap the `retrieve` method of the `Responses` class to trace it."""
    # https://github.com/openai/openai-python/blob/dc68b90655912886bd7a6c7787f96005452ebfc9/src/openai/resources/responses/responses.py#L1417C9-L1417C17
    retrieval_enum = getattr(
        GenAIAttributes.GenAiOperationNameValues, "RETRIEVAL", None
    )
    operation_name = retrieval_enum.value if retrieval_enum else "retrieval"

    def traced_method(wrapped, instance, args, kwargs):
        from opentelemetry.util.genai.types import (  # pylint: disable=import-outside-toplevel
            Error,
            LLMInvocation,
        )

        span_attributes = get_llm_request_attributes(
            {},
            instance,
            operation_name,
        )
        request_model = str(
            span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
            or "unknown"
        )
        streaming = is_streaming(kwargs)

        capture_content = _should_capture_content()
        invocation = handler.start_llm(
            LLMInvocation(
                request_model=request_model,
                operation_name=operation_name,
                provider=OPENAI,
                attributes=span_attributes.copy(),
                metric_attributes={
                    GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name
                },
            )
        )

        try:
            result = wrapped(*args, **kwargs)
            if hasattr(result, "parse"):
                parsed_result = result.parse()
            else:
                parsed_result = result

            if streaming:
                return ResponseStreamWrapper(
                    parsed_result,
                    handler,
                    invocation,
                    capture_content,
                )

            _set_invocation_response_attributes(
                invocation, parsed_result, capture_content
            )
            handler.stop_llm(invocation)
            return result

        except Exception as error:
            handler.fail_llm(
                invocation, Error(message=str(error), type=type(error))
            )
            raise

    return traced_method


# ---------------------------------------------------------------------------
# Response attribute extraction
# ---------------------------------------------------------------------------


def _set_invocation_response_attributes(
    invocation: "LLMInvocation",
    result: Any,
    capture_content: bool,
):
    if result is None:
        return

    if getattr(result, "model", None) and (
        not invocation.request_model
        or invocation.request_model == "unknown"
    ):
        invocation.request_model = result.model

    if getattr(result, "model", None):
        invocation.response_model_name = result.model

    if getattr(result, "id", None):
        invocation.response_id = result.id

    if getattr(result, "service_tier", None):
        invocation.attributes[
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER
        ] = result.service_tier

    if getattr(result, "usage", None):
        input_tokens = getattr(result.usage, "input_tokens", None)
        if input_tokens is None:
            input_tokens = getattr(result.usage, "prompt_tokens", None)
        invocation.input_tokens = input_tokens

        output_tokens = getattr(result.usage, "output_tokens", None)
        if output_tokens is None:
            output_tokens = getattr(result.usage, "completion_tokens", None)
        invocation.output_tokens = output_tokens

    if capture_content:
        output_messages = _extract_output_messages(result)
        if output_messages:
            invocation.output_messages = output_messages


# ---------------------------------------------------------------------------
# Stream wrappers
# ---------------------------------------------------------------------------


class _ResponseProxy:
    def __init__(self, response, finalize):
        self._response = response
        self._finalize = finalize

    def close(self):
        try:
            self._response.close()
        finally:
            self._finalize(None)

    def __getattr__(self, name):
        return getattr(self._response, name)


class ResponseStreamWrapper:
    """Wrapper for OpenAI Responses API streams using TelemetryHandler."""

    def __init__(
        self,
        stream: Any,
        handler: "TelemetryHandler",
        invocation: "LLMInvocation",
        capture_content: bool,
    ):
        self.stream = stream
        self.handler = handler
        self.invocation = invocation
        self._capture_content = capture_content
        self._finalized = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self._fail(str(exc_val), type(exc_val) if exc_val else Exception)
        finally:
            self.close()
        return False

    def close(self):
        if hasattr(self.stream, "close"):
            self.stream.close()
        self._stop(None)

    def __iter__(self):
        return self

    def __next__(self):
        try:
            event = next(self.stream)
            self.process_event(event)
            return event
        except StopIteration:
            self._stop(None)
            raise
        except Exception as error:
            self._fail(str(error), type(error))
            raise

    def get_final_response(self):
        if not hasattr(self.stream, "get_final_response"):
            raise AttributeError("get_final_response is not available")
        self.until_done()
        return self.stream.get_final_response()

    def until_done(self):
        for _ in self:
            pass
        return self

    def parse(self):
        """Called when using with_raw_response with stream=True"""
        return self

    def __getattr__(self, name):
        return getattr(self.stream, name)

    @property
    def response(self):
        response = getattr(self.stream, "response", None)
        if response is None:
            return None
        return _ResponseProxy(response, lambda *_: self._stop(None))

    def _stop(self, result: Any):
        if self._finalized:
            return
        _set_invocation_response_attributes(
            self.invocation, result, self._capture_content
        )
        self.handler.stop_llm(self.invocation)
        self._finalized = True

    def _fail(self, message: str, error_type: type[BaseException]):
        if self._finalized:
            return
        from opentelemetry.util.genai.types import (  # pylint: disable=import-outside-toplevel
            Error,
        )

        self.handler.fail_llm(
            self.invocation, Error(message=message, type=error_type)
        )
        self._finalized = True

    def process_event(self, event):
        event_type = getattr(event, "type", None)
        response = getattr(event, "response", None)

        if response and (
            not self.invocation.request_model
            or self.invocation.request_model == "unknown"
        ):
            model = getattr(response, "model", None)
            if model:
                self.invocation.request_model = model

        if event_type == "response.completed":
            self._stop(response)
            return

        if event_type in {"response.failed", "response.incomplete"}:
            _set_invocation_response_attributes(
                self.invocation, response, self._capture_content
            )
            self._fail(event_type, RuntimeError)
            return

        if event_type == "error":
            error_type = getattr(event, "code", None) or "response.error"
            message = getattr(event, "message", None) or error_type
            self._fail(message, RuntimeError)
            return
