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

from __future__ import annotations

import json
from enum import Enum
from os import environ
from typing import Mapping, Optional, Union
from urllib.parse import urlparse

from httpx import URL
from openai import NotGiven

from opentelemetry._logs import LogRecord
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.trace import Span
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)
from opentelemetry.trace.status import Status, StatusCode

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MODE = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MODE"
)


class CaptureMode(Enum):
    """Capture mode for GenAI instrumentation.

    METADATA: Only capture metadata (token counts, model, finish reasons).
              No message content, no log events. This is the default.
    ALL: Capture everything including message content and log events.
    """

    METADATA = "metadata"
    ALL = "all"


# Package-specific default modes
# LLM clients default to metadata (avoid sensitive data)
# Frameworks default to all (need full context for debugging)
PACKAGE_DEFAULT_MODES: dict[str, CaptureMode] = {
    "openai": CaptureMode.METADATA,
    "langgraph": CaptureMode.ALL,
    "langchain": CaptureMode.ALL,
}


# Custom attribute names not in semantic conventions yet
LLM_REQUEST_USER = "gen_ai.openai.request.user"
LLM_REQUEST_STREAMING = "gen_ai.request.streaming"
LLM_REQUEST_REASONING_EFFORT = "gen_ai.openai.request.reasoning_effort"
LLM_REQUEST_STRUCTURED_OUTPUT_SCHEMA = "gen_ai.request.response_format.schema"
LLM_OPENAI_API_BASE = "gen_ai.openai.api_base"
LLM_OPENAI_API_VERSION = "gen_ai.openai.api_version"
LLM_USAGE_TOTAL_TOKENS = "llm.usage.total_tokens"
LLM_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.input_tokens_details.cached"
LLM_USAGE_REASONING_TOKENS = "gen_ai.usage.output_tokens_details.reasoning"

# Span attributes for input/output content (when capture_content is enabled)
LLM_REQUEST_MESSAGES = "gen_ai.request.messages"
LLM_RESPONSE_CONTENT = "gen_ai.response.content"
LLM_REQUEST_PROMPT = "gen_ai.request.prompt"
LLM_REQUEST_INPUT = "gen_ai.request.input"


def is_content_enabled() -> bool:
    capture_content = environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
    )

    return capture_content.lower() == "true"


def get_capture_mode(package_name: Optional[str] = None) -> CaptureMode:
    """Determine the capture mode from environment variables.

    Resolution order:
    1. Package-specific env var (OTEL_INSTRUMENTATION_{PACKAGE}_CAPTURE_MODE)
    2. Global env var (OTEL_INSTRUMENTATION_GENAI_CAPTURE_MODE)
    3. Legacy env var (OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT)
    4. Package-specific default

    Args:
        package_name: Package name (e.g., "openai", "langgraph").
                      If None, uses global config only.

    Returns:
        CaptureMode.METADATA or CaptureMode.ALL
    """
    # 1. Check package-specific env var
    if package_name:
        pkg_env_var = f"OTEL_INSTRUMENTATION_{package_name.upper()}_CAPTURE_MODE"
        pkg_mode = environ.get(pkg_env_var, "").strip().strip('"').strip("'").lower()
        if pkg_mode == "all":
            return CaptureMode.ALL
        if pkg_mode == "metadata":
            return CaptureMode.METADATA

    # 2. Check global env var
    global_mode = environ.get(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MODE, "")
    global_mode = global_mode.strip().strip('"').strip("'").lower()
    if global_mode == "all":
        return CaptureMode.ALL
    if global_mode == "metadata":
        return CaptureMode.METADATA

    # 3. Check legacy env var
    if is_content_enabled():
        return CaptureMode.ALL

    # 4. Package-specific default
    if package_name:
        return PACKAGE_DEFAULT_MODES.get(package_name, CaptureMode.METADATA)

    return CaptureMode.METADATA


def get_vendor_from_base_url(base_url: str) -> str:
    """Detect the vendor/provider from the base URL.

    Supports OpenAI, Azure, AWS Bedrock, Google Vertex, and OpenRouter.
    """
    if not base_url:
        return GenAIAttributes.GenAiSystemValues.OPENAI.value

    base_url_lower = base_url.lower()

    if "openai.azure.com" in base_url_lower:
        return "azure"
    if "amazonaws.com" in base_url_lower or "bedrock" in base_url_lower:
        return "aws_bedrock"
    if "googleapis.com" in base_url_lower or "vertex" in base_url_lower:
        return "google_vertex"
    if "openrouter.ai" in base_url_lower:
        return "openrouter"

    return GenAIAttributes.GenAiSystemValues.OPENAI.value


def get_base_url(client_instance) -> Optional[str]:
    """Extract the base URL from the client instance."""
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return None

    if isinstance(base_url, URL):
        return str(base_url)
    return base_url


def get_api_version(client_instance) -> Optional[str]:
    """Extract the API version from the client (Azure OpenAI)."""
    try:
        import openai

        base_client = getattr(client_instance, "_client", None)
        if isinstance(
            base_client, (openai.AsyncAzureOpenAI, openai.AzureOpenAI)
        ):
            return getattr(base_client, "_api_version", None)
    except (ImportError, AttributeError):
        pass
    return None


def extract_tool_calls(item, capture_content):
    tool_calls = get_property_value(item, "tool_calls")
    if tool_calls is None:
        return None

    calls = []
    for tool_call in tool_calls:
        tool_call_dict = {}
        call_id = get_property_value(tool_call, "id")
        if call_id:
            tool_call_dict["id"] = call_id

        tool_type = get_property_value(tool_call, "type")
        if tool_type:
            tool_call_dict["type"] = tool_type

        func = get_property_value(tool_call, "function")
        if func:
            tool_call_dict["function"] = {}

            name = get_property_value(func, "name")
            if name:
                tool_call_dict["function"]["name"] = name

            arguments = get_property_value(func, "arguments")
            if capture_content and arguments:
                if isinstance(arguments, str):
                    arguments = arguments.replace("\n", "")
                tool_call_dict["function"]["arguments"] = arguments

        calls.append(tool_call_dict)
    return calls


def set_server_address_and_port(client_instance, attributes):
    base_client = getattr(client_instance, "_client", None)
    base_url = getattr(base_client, "base_url", None)
    if not base_url:
        return

    port = -1
    if isinstance(base_url, URL):
        attributes[ServerAttributes.SERVER_ADDRESS] = base_url.host
        port = base_url.port
    elif isinstance(base_url, str):
        url = urlparse(base_url)
        attributes[ServerAttributes.SERVER_ADDRESS] = url.hostname
        port = url.port

    if port and port != 443 and port > 0:
        attributes[ServerAttributes.SERVER_PORT] = port


def get_property_value(obj, property_name):
    if isinstance(obj, dict):
        return obj.get(property_name, None)

    return getattr(obj, property_name, None)


def message_to_event(message, capture_content):
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
    }
    role = get_property_value(message, "role")
    content = get_property_value(message, "content")

    body = {}
    if capture_content and content:
        body["content"] = content
    if role == "assistant":
        tool_calls = extract_tool_calls(message, capture_content)
        if tool_calls:
            body = {"tool_calls": tool_calls}
    elif role == "tool":
        tool_call_id = get_property_value(message, "tool_call_id")
        if tool_call_id:
            body["id"] = tool_call_id

    return LogRecord(
        event_name=f"gen_ai.{role}.message",
        attributes=attributes,
        body=body if body else None,
    )


def choice_to_event(choice, capture_content):
    attributes = {
        GenAIAttributes.GEN_AI_SYSTEM: GenAIAttributes.GenAiSystemValues.OPENAI.value
    }

    body = {
        "index": choice.index,
        "finish_reason": choice.finish_reason or "error",
    }

    if choice.message:
        message = {
            "role": (
                choice.message.role
                if choice.message and choice.message.role
                else None
            )
        }
        tool_calls = extract_tool_calls(choice.message, capture_content)
        if tool_calls:
            message["tool_calls"] = tool_calls
        content = get_property_value(choice.message, "content")
        if capture_content and content:
            message["content"] = content
        body["message"] = message

    return LogRecord(
        event_name="gen_ai.choice",
        attributes=attributes,
        body=body,
    )


def set_span_attributes(span, attributes: dict):
    for field, value in attributes.model_dump(by_alias=True).items():
        set_span_attribute(span, field, value)


def set_span_attribute(span, name, value):
    if non_numerical_value_is_set(value) is False:
        return

    span.set_attribute(name, value)


def is_streaming(kwargs):
    return non_numerical_value_is_set(kwargs.get("stream"))


def non_numerical_value_is_set(value: bool | str | NotGiven | None):
    return bool(value) and value_is_set(value)


def value_is_set(value):
    return value is not None and not isinstance(value, NotGiven)


def set_tools_attributes(span: Span, kwargs: dict, capture_mode: CaptureMode = CaptureMode.METADATA):
    """Set span attributes for tool/function definitions in the request.

    In METADATA mode: Only captures tool names as a list.
    In ALL mode: Captures full tool details (name, description, parameters).
    """
    tools = kwargs.get("tools")
    if not tools:
        return

    tool_names = []
    for i, tool in enumerate(tools):
        if isinstance(tool, dict):
            function = tool.get("function")
        else:
            function = getattr(tool, "function", None)

        if not function:
            continue

        if isinstance(function, dict):
            name = function.get("name")
            description = function.get("description")
            parameters = function.get("parameters")
        else:
            name = getattr(function, "name", None)
            description = getattr(function, "description", None)
            parameters = getattr(function, "parameters", None)

        if name:
            tool_names.append(name)

            # In ALL mode, also set detailed attributes
            if capture_mode == CaptureMode.ALL:
                prefix = f"gen_ai.request.tools.{i}"
                span.set_attribute(f"{prefix}.name", name)
                if description:
                    span.set_attribute(f"{prefix}.description", description)
                if parameters:
                    try:
                        span.set_attribute(f"{prefix}.parameters", json.dumps(parameters))
                    except (TypeError, ValueError):
                        pass

    # Always set the simple list of tool names
    if tool_names:
        span.set_attribute("gen_ai.request.available_tools", tool_names)


def extract_structured_output_schema(response_format) -> Optional[str]:
    """Extract JSON schema from response_format for structured outputs."""
    if response_format is None:
        return None

    try:
        # Handle dict-style response_format with json_schema
        if isinstance(response_format, dict):
            if response_format.get("type") == "json_schema":
                json_schema = response_format.get("json_schema")
                if json_schema:
                    schema = json_schema.get("schema")
                    if schema:
                        return json.dumps(schema)

        # Handle Pydantic models
        try:
            import pydantic

            if isinstance(response_format, type) and issubclass(
                response_format, pydantic.BaseModel
            ):
                return json.dumps(response_format.model_json_schema())
            if hasattr(response_format, "model_json_schema") and callable(
                response_format.model_json_schema
            ):
                return json.dumps(response_format.model_json_schema())
        except ImportError:
            pass

        # Try TypeAdapter for other types
        try:
            import pydantic

            schema = pydantic.TypeAdapter(response_format).json_schema()
            return json.dumps(schema)
        except Exception:
            pass

    except Exception:
        pass

    return None


def get_llm_request_attributes(
    kwargs,
    client_instance,
    operation_name=GenAIAttributes.GenAiOperationNameValues.CHAT.value,
):
    # pylint: disable=too-many-branches

    # Get base URL and detect vendor
    base_url = get_base_url(client_instance)
    vendor = get_vendor_from_base_url(base_url) if base_url else (
        GenAIAttributes.GenAiSystemValues.OPENAI.value
    )

    attributes = {
        GenAIAttributes.GEN_AI_OPERATION_NAME: operation_name,
        GenAIAttributes.GEN_AI_SYSTEM: vendor,
        GenAIAttributes.GEN_AI_REQUEST_MODEL: kwargs.get("model"),
    }

    # Add API base URL
    if base_url:
        attributes[LLM_OPENAI_API_BASE] = base_url

    # Add Azure API version if applicable
    api_version = get_api_version(client_instance)
    if api_version:
        attributes[LLM_OPENAI_API_VERSION] = api_version

    # Add streaming indicator
    stream = kwargs.get("stream")
    if value_is_set(stream):
        attributes[LLM_REQUEST_STREAMING] = bool(stream)

    # Add user identifier
    user = kwargs.get("user")
    if value_is_set(user):
        attributes[LLM_REQUEST_USER] = user

    # Add chat-specific attributes only for chat operations
    if operation_name == GenAIAttributes.GenAiOperationNameValues.CHAT.value:
        attributes.update(
            {
                GenAIAttributes.GEN_AI_REQUEST_TEMPERATURE: kwargs.get(
                    "temperature"
                ),
                GenAIAttributes.GEN_AI_REQUEST_TOP_P: kwargs.get("p")
                or kwargs.get("top_p"),
                GenAIAttributes.GEN_AI_REQUEST_MAX_TOKENS: kwargs.get(
                    "max_tokens"
                ),
                GenAIAttributes.GEN_AI_REQUEST_PRESENCE_PENALTY: kwargs.get(
                    "presence_penalty"
                ),
                GenAIAttributes.GEN_AI_REQUEST_FREQUENCY_PENALTY: kwargs.get(
                    "frequency_penalty"
                ),
                GenAIAttributes.GEN_AI_REQUEST_SEED: kwargs.get("seed"),
            }
        )

        # Add reasoning effort for o1/o3 models
        reasoning_effort = kwargs.get("reasoning_effort")
        if value_is_set(reasoning_effort):
            attributes[LLM_REQUEST_REASONING_EFFORT] = reasoning_effort

        if (choice_count := kwargs.get("n")) is not None:
            # Only add non default, meaningful values
            if isinstance(choice_count, int) and choice_count != 1:
                attributes[GenAIAttributes.GEN_AI_REQUEST_CHOICE_COUNT] = (
                    choice_count
                )

        if (stop_sequences := kwargs.get("stop")) is not None:
            if isinstance(stop_sequences, str):
                stop_sequences = [stop_sequences]
            attributes[GenAIAttributes.GEN_AI_REQUEST_STOP_SEQUENCES] = (
                stop_sequences
            )

        if (response_format := kwargs.get("response_format")) is not None:
            # response_format may be string or object with a string in the
            # `type` key
            if isinstance(response_format, Mapping):
                if (
                    response_format_type := response_format.get("type")
                ) is not None:
                    attributes[
                        GenAIAttributes.GEN_AI_OPENAI_REQUEST_RESPONSE_FORMAT
                    ] = response_format_type

                # Extract structured output schema
                schema = extract_structured_output_schema(response_format)
                if schema:
                    attributes[LLM_REQUEST_STRUCTURED_OUTPUT_SCHEMA] = schema
            else:
                attributes[
                    GenAIAttributes.GEN_AI_OPENAI_REQUEST_RESPONSE_FORMAT
                ] = response_format

        # service_tier can be passed directly or in extra_body
        # (in SDK 1.26.0 it's via extra_body)
        service_tier = kwargs.get("service_tier")
        if service_tier is None:
            extra_body = kwargs.get("extra_body")
            if isinstance(extra_body, Mapping):
                service_tier = extra_body.get("service_tier")
        attributes[GenAIAttributes.GEN_AI_OPENAI_REQUEST_SERVICE_TIER] = (
            service_tier if service_tier != "auto" else None
        )

    # Add embeddings-specific attributes
    elif (
        operation_name
        == GenAIAttributes.GenAiOperationNameValues.EMBEDDINGS.value
    ):
        # Add embedding dimensions if specified
        if (dimensions := kwargs.get("dimensions")) is not None:
            # TODO: move to GEN_AI_EMBEDDINGS_DIMENSION_COUNT
            # when 1.39.0 is baseline
            attributes["gen_ai.embeddings.dimension.count"] = dimensions

        # Add encoding format if specified
        if "encoding_format" in kwargs:
            attributes[GenAIAttributes.GEN_AI_REQUEST_ENCODING_FORMATS] = [
                kwargs["encoding_format"]
            ]

    set_server_address_and_port(client_instance, attributes)

    # filter out values not set
    return {k: v for k, v in attributes.items() if value_is_set(v)}


def set_response_attributes(span: Span, result):
    """Set common response attributes on a span."""
    if not span.is_recording():
        return

    if getattr(result, "model", None):
        set_span_attribute(
            span, GenAIAttributes.GEN_AI_RESPONSE_MODEL, result.model
        )

    if getattr(result, "id", None):
        set_span_attribute(span, GenAIAttributes.GEN_AI_RESPONSE_ID, result.id)

    if getattr(result, "service_tier", None):
        set_span_attribute(
            span,
            GenAIAttributes.GEN_AI_OPENAI_RESPONSE_SERVICE_TIER,
            result.service_tier,
        )

    if getattr(result, "system_fingerprint", None):
        set_span_attribute(
            span,
            "gen_ai.openai.response.system_fingerprint",
            result.system_fingerprint,
        )

    # Set usage attributes
    usage = getattr(result, "usage", None)
    if usage:
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)

        if prompt_tokens is not None:
            set_span_attribute(
                span, GenAIAttributes.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens
            )

        if completion_tokens is not None:
            set_span_attribute(
                span,
                GenAIAttributes.GEN_AI_USAGE_OUTPUT_TOKENS,
                completion_tokens,
            )

        # Set total tokens
        if prompt_tokens is not None and completion_tokens is not None:
            set_span_attribute(
                span,
                LLM_USAGE_TOTAL_TOKENS,
                prompt_tokens + completion_tokens,
            )

        # Set cached tokens from prompt_tokens_details
        prompt_tokens_details = getattr(usage, "prompt_tokens_details", None)
        if prompt_tokens_details:
            cached_tokens = getattr(
                prompt_tokens_details, "cached_tokens", None
            )
            if cached_tokens is not None and cached_tokens > 0:
                set_span_attribute(
                    span, LLM_USAGE_CACHE_READ_INPUT_TOKENS, cached_tokens
                )

        # Set reasoning tokens from completion_tokens_details (o1/o3 models)
        completion_tokens_details = getattr(
            usage, "completion_tokens_details", None
        )
        if completion_tokens_details:
            reasoning_tokens = getattr(
                completion_tokens_details, "reasoning_tokens", None
            )
            if reasoning_tokens is not None and reasoning_tokens > 0:
                set_span_attribute(
                    span, LLM_USAGE_REASONING_TOKENS, reasoning_tokens
                )


def propagate_trace_context(span: Span, kwargs: dict):
    """Inject W3C trace context into request headers.

    This enables end-to-end tracing when the backend supports it.
    """
    extra_headers = kwargs.get("extra_headers")
    if extra_headers is None:
        extra_headers = {}
    elif not isinstance(extra_headers, dict):
        # If extra_headers is not a dict, we can't inject
        return

    # Make a copy to avoid mutating the original
    extra_headers = dict(extra_headers)

    ctx = set_span_in_context(span)
    TraceContextTextMapPropagator().inject(extra_headers, context=ctx)

    kwargs["extra_headers"] = extra_headers


def handle_span_exception(span, error):
    span.set_status(Status(StatusCode.ERROR, str(error)))
    if span.is_recording():
        span.set_attribute(
            ErrorAttributes.ERROR_TYPE, type(error).__qualname__
        )
    span.end()


def set_request_content_on_span(
    span: Span, kwargs: dict, capture_mode: Union[CaptureMode, bool]
):
    """Set request messages/prompt as span attributes when content capture is enabled."""
    # Support both CaptureMode enum and legacy bool for backward compat
    if isinstance(capture_mode, bool):
        should_capture = capture_mode
    else:
        should_capture = capture_mode == CaptureMode.ALL

    if not should_capture or not span.is_recording():
        return

    # For chat completions - capture messages
    messages = kwargs.get("messages")
    if messages:
        try:
            messages_str = json.dumps(messages, default=str)
            span.set_attribute(LLM_REQUEST_MESSAGES, messages_str)
        except (TypeError, ValueError):
            pass
        return

    # For legacy completions - capture prompt
    prompt = kwargs.get("prompt")
    if prompt:
        if isinstance(prompt, list):
            prompt_str = json.dumps(prompt)
        else:
            prompt_str = str(prompt)
        span.set_attribute(LLM_REQUEST_PROMPT, prompt_str)
        return

    # For embeddings - capture input
    input_text = kwargs.get("input")
    if input_text:
        if isinstance(input_text, list):
            input_str = json.dumps(input_text)
        else:
            input_str = str(input_text)
        span.set_attribute(LLM_REQUEST_INPUT, input_str)


def set_response_content_on_span(
    span: Span, result, capture_mode: Union[CaptureMode, bool]
):
    """Set response content as span attributes when content capture is enabled."""
    # Support both CaptureMode enum and legacy bool for backward compat
    if isinstance(capture_mode, bool):
        should_capture = capture_mode
    else:
        should_capture = capture_mode == CaptureMode.ALL

    if not should_capture or not span.is_recording():
        return

    # For chat completions - capture choice messages
    choices = getattr(result, "choices", None)
    if choices:
        response_parts = []
        for choice in choices:
            message = getattr(choice, "message", None)
            if message:
                content = getattr(message, "content", None)
                if content:
                    response_parts.append(content)
                # Also capture tool calls
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        func = getattr(tc, "function", None)
                        if func:
                            name = getattr(func, "name", "")
                            args = getattr(func, "arguments", "")
                            response_parts.append(f"[Tool: {name}({args})]")
            # For legacy completions
            text = getattr(choice, "text", None)
            if text:
                response_parts.append(text)

        if response_parts:
            span.set_attribute(LLM_RESPONSE_CONTENT, "\n---\n".join(response_parts))
        return

    # For responses API
    output = getattr(result, "output", None)
    if output:
        try:
            output_str = json.dumps(output, default=str)
            span.set_attribute(LLM_RESPONSE_CONTENT, output_str)
        except (TypeError, ValueError):
            pass
