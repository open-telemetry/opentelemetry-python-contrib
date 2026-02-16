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

from typing import TYPE_CHECKING, Any, Mapping, Optional

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)

try:
    from opentelemetry.util.genai.types import (
        Error,
        InputMessage,
        LLMInvocation,
        OutputMessage,
        Text,
    )
except (
    ModuleNotFoundError
):  # pragma: no cover - optional dependency at import-time
    Error = InputMessage = LLMInvocation = OutputMessage = Text = None  # type: ignore[assignment,misc]

from .utils import (
    get_llm_request_attributes,
    is_streaming,
)

if TYPE_CHECKING:
    from opentelemetry.util.genai.handler import TelemetryHandler

OPENAI = GenAIAttributes.GenAiSystemValues.OPENAI.value
GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)


def _extract_system_instruction(kwargs: dict):
    """Extract system instruction from the ``instructions`` parameter."""
    if Text is None:
        return []
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
    if InputMessage is None or Text is None:
        return []
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
    if OutputMessage is None or Text is None:
        return []
    if result is None:
        return []

    output_items = getattr(result, "output", None)
    if not output_items:
        return []

    messages = []
    for item in output_items:
        if getattr(item, "type", None) != "message":
            continue

        role = getattr(item, "role", "assistant")
        finish_reason = _finish_reason_from_status(
            getattr(item, "status", None)
        )
        parts = _extract_output_parts(getattr(item, "content", []), Text)

        messages.append(
            OutputMessage(role=role, parts=parts, finish_reason=finish_reason)
        )

    return messages


def _finish_reason_from_status(status):
    return "stop" if status == "completed" else (status or "stop")


def _extract_output_parts(content_blocks, text_type):
    parts = []
    for block in content_blocks:
        block_type = getattr(block, "type", None)
        if block_type == "output_text":
            text = getattr(block, "text", None)
            if text:
                parts.append(text_type(content=text))
        elif block_type == "refusal":
            refusal = getattr(block, "refusal", None)
            if refusal:
                parts.append(text_type(content=refusal))
    return parts


def _extract_finish_reasons(result: Any) -> list[str]:
    """Extract finish reasons from Responses API output items."""
    output_items = getattr(result, "output", None)
    if not output_items:
        return []

    finish_reasons = []
    for item in output_items:
        if getattr(item, "type", None) != "message":
            continue
        finish_reasons.append(
            _finish_reason_from_status(getattr(item, "status", None))
        )
    return finish_reasons


def _extract_output_type(kwargs: dict) -> Optional[str]:
    """Extract output type from Responses API request text.format."""
    text_config = kwargs.get("text")
    if not isinstance(text_config, Mapping):
        return None

    format_config = text_config.get("format")
    if isinstance(format_config, Mapping):
        format_type = format_config.get("type")
    else:
        format_type = None

    if format_type == "json_schema":
        return "json"
    return format_type


def _get_field(obj: Any, key: str):
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _set_optional_attribute(
    invocation: "LLMInvocation",
    result: Any,
    source_name: str,
    target_name: str,
):
    value = getattr(result, source_name, None)
    if value is not None:
        invocation.attributes[target_name] = value


def _set_invocation_usage_attributes(invocation: "LLMInvocation", usage: Any):
    input_tokens = _get_field(usage, "input_tokens")
    if input_tokens is None:
        input_tokens = _get_field(usage, "prompt_tokens")
    invocation.input_tokens = input_tokens

    output_tokens = _get_field(usage, "output_tokens")
    if output_tokens is None:
        output_tokens = _get_field(usage, "completion_tokens")
    invocation.output_tokens = output_tokens

    input_token_details = _get_field(usage, "input_tokens_details")
    if input_token_details is None:
        input_token_details = _get_field(usage, "prompt_tokens_details")

    cache_read_tokens = _get_field(input_token_details, "cached_tokens")
    if cache_read_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS] = (
            cache_read_tokens
        )

    cache_creation_tokens = _get_field(
        input_token_details, "cache_creation_input_tokens"
    )
    if cache_creation_tokens is not None:
        invocation.attributes[GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS] = (
            cache_creation_tokens
        )


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
        if Error is None or LLMInvocation is None:
            raise ModuleNotFoundError(
                "opentelemetry.util.genai.types is unavailable"
            )

        operation_name = GenAIAttributes.GenAiOperationNameValues.CHAT.value
        span_attributes = get_llm_request_attributes(
            kwargs,
            instance,
            operation_name,
        )
        output_type = _extract_output_type(kwargs)
        if output_type:
            span_attributes[GenAIAttributes.GEN_AI_OUTPUT_TYPE] = output_type
        request_model = str(
            span_attributes.get(GenAIAttributes.GEN_AI_REQUEST_MODEL)
            or "unknown"
        )
        streaming = is_streaming(kwargs)

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
        not invocation.request_model or invocation.request_model == "unknown"
    ):
        invocation.request_model = result.model

    if getattr(result, "model", None):
        invocation.response_model_name = result.model

    if getattr(result, "id", None):
        invocation.response_id = result.id

    _set_optional_attribute(
        invocation,
        result,
        "service_tier",
        GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
    )
    _set_optional_attribute(
        invocation,
        result,
        "system_fingerprint",
        GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SYSTEM_FINGERPRINT,
    )

    usage = getattr(result, "usage", None)
    if usage:
        _set_invocation_usage_attributes(invocation, usage)

    finish_reasons = _extract_finish_reasons(result)
    if finish_reasons:
        invocation.finish_reasons = finish_reasons

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
                self._fail(
                    str(exc_val), type(exc_val) if exc_val else Exception
                )
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
        if Error is None:
            raise ModuleNotFoundError(
                "opentelemetry.util.genai.types is unavailable"
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
