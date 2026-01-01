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

"""Patching functions for MCP instrumentation."""

from __future__ import annotations

import logging
from typing import Any, Callable

from opentelemetry import context as context_api
from opentelemetry._logs import Logger
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.trace.status import Status, StatusCode

from opentelemetry.instrumentation.mcp.utils import (
    dont_throw,
    is_content_enabled,
    safe_json_dumps,
    set_span_attribute,
)

logger = logging.getLogger(__name__)


def create_call_tool_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for ClientSession.call_tool."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        tool_name = args[0] if args else kwargs.get("name", "unknown")
        arguments = kwargs.get("arguments", {})

        with tracer.start_as_current_span(
            f"mcp.call_tool {tool_name}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mcp",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "execute_tool",
                "mcp.tool.name": tool_name,
            },
        ) as span:
            if is_content_enabled() and arguments:
                set_span_attribute(span, "mcp.tool.arguments", safe_json_dumps(arguments))

            try:
                response = await wrapped(*args, **kwargs)

                if span.is_recording():
                    if hasattr(response, "content") and response.content:
                        set_span_attribute(span, "mcp.response.content_count", len(response.content))
                    if hasattr(response, "isError"):
                        set_span_attribute(span, "mcp.response.is_error", response.isError)
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_list_tools_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for ClientSession.list_tools."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "mcp.list_tools",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mcp",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "list_tools",
            },
        ) as span:
            try:
                response = await wrapped(*args, **kwargs)

                if span.is_recording():
                    if hasattr(response, "tools"):
                        set_span_attribute(span, "mcp.tools.count", len(response.tools))
                        tool_names = [t.name for t in response.tools if hasattr(t, "name")]
                        if tool_names:
                            set_span_attribute(span, "mcp.tools.names", tool_names)
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_list_resources_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for ClientSession.list_resources."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "mcp.list_resources",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mcp",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "list_resources",
            },
        ) as span:
            try:
                response = await wrapped(*args, **kwargs)

                if span.is_recording():
                    if hasattr(response, "resources"):
                        set_span_attribute(span, "mcp.resources.count", len(response.resources))
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_read_resource_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for ClientSession.read_resource."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        uri = args[0] if args else kwargs.get("uri", "unknown")

        with tracer.start_as_current_span(
            "mcp.read_resource",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mcp",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "read_resource",
                "mcp.resource.uri": str(uri),
            },
        ) as span:
            try:
                response = await wrapped(*args, **kwargs)

                if span.is_recording():
                    if hasattr(response, "contents") and response.contents:
                        set_span_attribute(span, "mcp.resource.contents_count", len(response.contents))
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_list_prompts_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for ClientSession.list_prompts."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "mcp.list_prompts",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mcp",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "list_prompts",
            },
        ) as span:
            try:
                response = await wrapped(*args, **kwargs)

                if span.is_recording():
                    if hasattr(response, "prompts"):
                        set_span_attribute(span, "mcp.prompts.count", len(response.prompts))
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_get_prompt_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for ClientSession.get_prompt."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        prompt_name = args[0] if args else kwargs.get("name", "unknown")
        arguments = kwargs.get("arguments", {})

        with tracer.start_as_current_span(
            f"mcp.get_prompt {prompt_name}",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mcp",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "get_prompt",
                "mcp.prompt.name": prompt_name,
            },
        ) as span:
            if is_content_enabled() and arguments:
                set_span_attribute(span, "mcp.prompt.arguments", safe_json_dumps(arguments))

            try:
                response = await wrapped(*args, **kwargs)

                if span.is_recording():
                    if hasattr(response, "messages") and response.messages:
                        set_span_attribute(span, "mcp.prompt.messages_count", len(response.messages))
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper


def create_initialize_wrapper(tracer: Tracer, event_logger: Logger) -> Callable:
    """Create a wrapper for ClientSession.initialize."""

    async def wrapper(wrapped, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await wrapped(*args, **kwargs)

        with tracer.start_as_current_span(
            "mcp.initialize",
            kind=SpanKind.CLIENT,
            attributes={
                GenAIAttributes.GEN_AI_SYSTEM: "mcp",
                GenAIAttributes.GEN_AI_OPERATION_NAME: "initialize",
            },
        ) as span:
            try:
                response = await wrapped(*args, **kwargs)

                if span.is_recording():
                    if hasattr(response, "protocolVersion"):
                        set_span_attribute(span, "mcp.protocol_version", response.protocolVersion)
                    if hasattr(response, "serverInfo"):
                        info = response.serverInfo
                        if hasattr(info, "name"):
                            set_span_attribute(span, "mcp.server.name", info.name)
                        if hasattr(info, "version"):
                            set_span_attribute(span, "mcp.server.version", info.version)
                    span.set_status(Status(StatusCode.OK))

                return response
            except Exception as error:
                span.set_status(Status(StatusCode.ERROR, str(error)))
                if span.is_recording():
                    span.set_attribute("error.type", type(error).__qualname__)
                raise

    return wrapper
