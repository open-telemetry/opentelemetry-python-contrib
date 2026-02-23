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

"""Wrapping functions for Mem0 Memory class methods."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, StatusCode

_TRACER_NAME = "opentelemetry.instrumentation.mem0"


def _attr(name: str, fallback: str) -> str:
    return getattr(GenAIAttributes, name, fallback)


GEN_AI_OPERATION_NAME = _attr("GEN_AI_OPERATION_NAME", "gen_ai.operation.name")
GEN_AI_SYSTEM = _attr("GEN_AI_SYSTEM", "gen_ai.system")
GEN_AI_MEMORY_STORE_ID = _attr(
    "GEN_AI_MEMORY_STORE_ID", "gen_ai.memory.store.id"
)
GEN_AI_MEMORY_STORE_NAME = _attr(
    "GEN_AI_MEMORY_STORE_NAME", "gen_ai.memory.store.name"
)
GEN_AI_MEMORY_ID = _attr("GEN_AI_MEMORY_ID", "gen_ai.memory.id")
GEN_AI_MEMORY_SCOPE = _attr("GEN_AI_MEMORY_SCOPE", "gen_ai.memory.scope")
GEN_AI_MEMORY_QUERY = _attr("GEN_AI_MEMORY_QUERY", "gen_ai.memory.query")
GEN_AI_MEMORY_CONTENT = _attr("GEN_AI_MEMORY_CONTENT", "gen_ai.memory.content")
GEN_AI_MEMORY_SEARCH_RESULT_COUNT = _attr(
    "GEN_AI_MEMORY_SEARCH_RESULT_COUNT", "gen_ai.memory.search.result.count"
)
GEN_AI_MEMORY_NAMESPACE = _attr(
    "GEN_AI_MEMORY_NAMESPACE", "gen_ai.memory.namespace"
)


def _capture_content() -> bool:
    return os.environ.get(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", ""
    ).lower() in ("true", "1")


def _scope_from_kwargs(kwargs: dict[str, Any]) -> Optional[str]:
    """Infer memory scope from Mem0 filter kwargs."""
    if kwargs.get("user_id"):
        return "user"
    if kwargs.get("agent_id"):
        return "agent"
    if kwargs.get("run_id"):
        return "session"
    return None


def _set_common_attributes(
    span: trace.Span,
    operation: str,
    kwargs: dict[str, Any],
) -> None:
    span.set_attribute(GEN_AI_OPERATION_NAME, operation)
    span.set_attribute(GEN_AI_SYSTEM, "mem0")

    scope = _scope_from_kwargs(kwargs)
    if scope:
        span.set_attribute(GEN_AI_MEMORY_SCOPE, scope)

    user_id = kwargs.get("user_id")
    agent_id = kwargs.get("agent_id")
    if user_id:
        span.set_attribute(GEN_AI_MEMORY_NAMESPACE, f"user:{user_id}")
    elif agent_id:
        span.set_attribute(GEN_AI_MEMORY_NAMESPACE, f"agent:{agent_id}")


def wrap_memory_add(
    tracer_provider: Optional[trace.TracerProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(_TRACER_NAME, tracer_provider=tracer_provider)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        span_name = "update_memory mem0"
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "update_memory", kwargs)

            if _capture_content() and args:
                messages = args[0] if args else kwargs.get("messages")
                if messages and isinstance(messages, str):
                    span.set_attribute(GEN_AI_MEMORY_CONTENT, messages)

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise

            if isinstance(result, dict) and result.get("results"):
                for item in result["results"]:
                    if isinstance(item, dict) and item.get("id"):
                        span.set_attribute(GEN_AI_MEMORY_ID, str(item["id"]))
                        break

            return result

    return wrapper


def wrap_memory_search(
    tracer_provider: Optional[trace.TracerProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(_TRACER_NAME, tracer_provider=tracer_provider)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        span_name = "search_memory mem0"
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "search_memory", kwargs)

            query = args[0] if args else kwargs.get("query")
            if _capture_content() and query and isinstance(query, str):
                span.set_attribute(GEN_AI_MEMORY_QUERY, query)

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise

            if isinstance(result, dict) and "results" in result:
                span.set_attribute(
                    GEN_AI_MEMORY_SEARCH_RESULT_COUNT,
                    len(result["results"]),
                )
            elif isinstance(result, list):
                span.set_attribute(
                    GEN_AI_MEMORY_SEARCH_RESULT_COUNT, len(result)
                )

            return result

    return wrapper


def wrap_memory_update(
    tracer_provider: Optional[trace.TracerProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(_TRACER_NAME, tracer_provider=tracer_provider)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        memory_id = args[0] if args else kwargs.get("memory_id")
        span_name = "update_memory mem0"
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "update_memory", kwargs)
            if memory_id:
                span.set_attribute(GEN_AI_MEMORY_ID, str(memory_id))

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise

            return result

    return wrapper


def wrap_memory_delete(
    tracer_provider: Optional[trace.TracerProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(_TRACER_NAME, tracer_provider=tracer_provider)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        memory_id = args[0] if args else kwargs.get("memory_id")
        span_name = "delete_memory mem0"
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "delete_memory", kwargs)
            if memory_id:
                span.set_attribute(GEN_AI_MEMORY_ID, str(memory_id))

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise

            return result

    return wrapper


def wrap_memory_delete_all(
    tracer_provider: Optional[trace.TracerProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(_TRACER_NAME, tracer_provider=tracer_provider)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        span_name = "delete_memory mem0"
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "delete_memory", kwargs)

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise

            return result

    return wrapper


def wrap_memory_get_all(
    tracer_provider: Optional[trace.TracerProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(_TRACER_NAME, tracer_provider=tracer_provider)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        span_name = "search_memory mem0"
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "search_memory", kwargs)

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                span.set_status(StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                raise

            if isinstance(result, dict) and "results" in result:
                span.set_attribute(
                    GEN_AI_MEMORY_SEARCH_RESULT_COUNT,
                    len(result["results"]),
                )
            elif isinstance(result, list):
                span.set_attribute(
                    GEN_AI_MEMORY_SEARCH_RESULT_COUNT, len(result)
                )

            return result

    return wrapper
