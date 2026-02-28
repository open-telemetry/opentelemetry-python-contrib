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

"""Wrapping functions for Mem0 Memory class methods.

Each wrapper emits a CLIENT span with GenAI memory semantic convention
attributes, an ``error.type`` attribute on failure, and records a
``gen_ai.client.operation.duration`` histogram metric.
"""

from __future__ import annotations

import os
import timeit
from typing import Any, Callable, Optional

from opentelemetry import trace
from opentelemetry.metrics import MeterProvider, get_meter
from opentelemetry.semconv._incubating.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.util.genai.instruments import create_duration_histogram

_INSTRUMENTATION_NAME = "opentelemetry.instrumentation.mem0"

# ---------------------------------------------------------------------------
# Attribute constants — resolved at import time so they stay in sync with
# whichever semconv version is installed.
# ---------------------------------------------------------------------------


def _attr(name: str, fallback: str) -> str:
    return getattr(GenAIAttributes, name, fallback)


GEN_AI_OPERATION_NAME = _attr("GEN_AI_OPERATION_NAME", "gen_ai.operation.name")
GEN_AI_SYSTEM = _attr("GEN_AI_SYSTEM", "gen_ai.system")
GEN_AI_PROVIDER_NAME = _attr("GEN_AI_PROVIDER_NAME", "gen_ai.provider.name")
GEN_AI_MEMORY_STORE_ID = _attr(
    "GEN_AI_MEMORY_STORE_ID", "gen_ai.memory.store.id"
)
GEN_AI_MEMORY_STORE_NAME = _attr(
    "GEN_AI_MEMORY_STORE_NAME", "gen_ai.memory.store.name"
)
GEN_AI_MEMORY_ID = _attr("GEN_AI_MEMORY_ID", "gen_ai.memory.id")
GEN_AI_MEMORY_TYPE = _attr("GEN_AI_MEMORY_TYPE", "gen_ai.memory.type")
GEN_AI_MEMORY_SCOPE = _attr("GEN_AI_MEMORY_SCOPE", "gen_ai.memory.scope")
GEN_AI_MEMORY_QUERY = _attr("GEN_AI_MEMORY_QUERY", "gen_ai.memory.query")
GEN_AI_MEMORY_CONTENT = _attr("GEN_AI_MEMORY_CONTENT", "gen_ai.memory.content")
GEN_AI_MEMORY_NAMESPACE = _attr(
    "GEN_AI_MEMORY_NAMESPACE", "gen_ai.memory.namespace"
)
GEN_AI_MEMORY_SEARCH_RESULT_COUNT = _attr(
    "GEN_AI_MEMORY_SEARCH_RESULT_COUNT", "gen_ai.memory.search.result.count"
)
GEN_AI_MEMORY_UPDATE_STRATEGY = _attr(
    "GEN_AI_MEMORY_UPDATE_STRATEGY", "gen_ai.memory.update.strategy"
)
ERROR_TYPE = getattr(ErrorAttributes, "ERROR_TYPE", "error.type")

_PROVIDER = "mem0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _namespace_from_kwargs(kwargs: dict[str, Any]) -> Optional[str]:
    """Build namespace string from Mem0 identity kwargs."""
    user_id = kwargs.get("user_id")
    agent_id = kwargs.get("agent_id")
    if user_id:
        return f"user:{user_id}"
    if agent_id:
        return f"agent:{agent_id}"
    return None


def _set_common_attributes(
    span: trace.Span,
    operation: str,
    kwargs: dict[str, Any],
) -> None:
    """Set attributes shared by all memory operations."""
    span.set_attribute(GEN_AI_OPERATION_NAME, operation)
    span.set_attribute(GEN_AI_SYSTEM, _PROVIDER)
    span.set_attribute(GEN_AI_PROVIDER_NAME, _PROVIDER)

    scope = _scope_from_kwargs(kwargs)
    if scope:
        span.set_attribute(GEN_AI_MEMORY_SCOPE, scope)

    namespace = _namespace_from_kwargs(kwargs)
    if namespace:
        span.set_attribute(GEN_AI_MEMORY_NAMESPACE, namespace)


def _set_error(span: trace.Span, exc: BaseException) -> str:
    """Record error details on the span and return the error type string."""
    error_type = type(exc).__qualname__
    span.set_status(StatusCode.ERROR, str(exc))
    span.set_attribute(ERROR_TYPE, error_type)
    span.record_exception(exc)
    return error_type


def _record_duration(
    duration_histogram,
    duration_s: float,
    operation: str,
    error_type: Optional[str] = None,
) -> None:
    """Record the operation duration metric."""
    if duration_histogram is None:
        return
    attrs: dict[str, Any] = {
        GEN_AI_OPERATION_NAME: operation,
        GEN_AI_SYSTEM: _PROVIDER,
    }
    if error_type:
        attrs[ERROR_TYPE] = error_type
    duration_histogram.record(max(duration_s, 0.0), attributes=attrs)


def _result_count(result: Any) -> Optional[int]:
    """Extract result count from a Mem0 response (dict or list)."""
    if isinstance(result, dict) and "results" in result:
        return len(result["results"])
    if isinstance(result, list):
        return len(result)
    return None


def _first_memory_id(result: Any) -> Optional[str]:
    """Extract the first memory id from an add/update result."""
    if isinstance(result, dict) and result.get("results"):
        for item in result["results"]:
            if isinstance(item, dict) and item.get("id"):
                return str(item["id"])
    return None


# ---------------------------------------------------------------------------
# Wrapper factories
# ---------------------------------------------------------------------------


def wrap_memory_add(
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(
        _INSTRUMENTATION_NAME, tracer_provider=tracer_provider
    )
    meter = get_meter(_INSTRUMENTATION_NAME, meter_provider=meter_provider)
    duration_histogram = create_duration_histogram(meter)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        span_name = f"update_memory {_PROVIDER}"
        error_type = None
        start = timeit.default_timer()
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "update_memory", kwargs)
            # Mem0 add() is an upsert
            span.set_attribute(GEN_AI_MEMORY_UPDATE_STRATEGY, "merge")

            if _capture_content() and args:
                messages = args[0] if args else kwargs.get("messages")
                if messages and isinstance(messages, str):
                    span.set_attribute(GEN_AI_MEMORY_CONTENT, messages)

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                error_type = _set_error(span, exc)
                raise
            finally:
                _record_duration(
                    duration_histogram,
                    timeit.default_timer() - start,
                    "update_memory",
                    error_type,
                )

            mem_id = _first_memory_id(result)
            if mem_id:
                span.set_attribute(GEN_AI_MEMORY_ID, mem_id)

            return result

    return wrapper


def wrap_memory_search(
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(
        _INSTRUMENTATION_NAME, tracer_provider=tracer_provider
    )
    meter = get_meter(_INSTRUMENTATION_NAME, meter_provider=meter_provider)
    duration_histogram = create_duration_histogram(meter)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        span_name = f"search_memory {_PROVIDER}"
        error_type = None
        start = timeit.default_timer()
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
                error_type = _set_error(span, exc)
                raise
            finally:
                _record_duration(
                    duration_histogram,
                    timeit.default_timer() - start,
                    "search_memory",
                    error_type,
                )

            count = _result_count(result)
            if count is not None:
                span.set_attribute(GEN_AI_MEMORY_SEARCH_RESULT_COUNT, count)

            return result

    return wrapper


def wrap_memory_update(
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(
        _INSTRUMENTATION_NAME, tracer_provider=tracer_provider
    )
    meter = get_meter(_INSTRUMENTATION_NAME, meter_provider=meter_provider)
    duration_histogram = create_duration_histogram(meter)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        memory_id = args[0] if args else kwargs.get("memory_id")
        span_name = f"update_memory {_PROVIDER}"
        error_type = None
        start = timeit.default_timer()
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "update_memory", kwargs)
            span.set_attribute(GEN_AI_MEMORY_UPDATE_STRATEGY, "overwrite")
            if memory_id:
                span.set_attribute(GEN_AI_MEMORY_ID, str(memory_id))

            if _capture_content():
                data = kwargs.get("data")
                if data and isinstance(data, str):
                    span.set_attribute(GEN_AI_MEMORY_CONTENT, data)

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                error_type = _set_error(span, exc)
                raise
            finally:
                _record_duration(
                    duration_histogram,
                    timeit.default_timer() - start,
                    "update_memory",
                    error_type,
                )

            return result

    return wrapper


def wrap_memory_delete(
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(
        _INSTRUMENTATION_NAME, tracer_provider=tracer_provider
    )
    meter = get_meter(_INSTRUMENTATION_NAME, meter_provider=meter_provider)
    duration_histogram = create_duration_histogram(meter)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        memory_id = args[0] if args else kwargs.get("memory_id")
        span_name = f"delete_memory {_PROVIDER}"
        error_type = None
        start = timeit.default_timer()
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "delete_memory", kwargs)
            if memory_id:
                span.set_attribute(GEN_AI_MEMORY_ID, str(memory_id))

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                error_type = _set_error(span, exc)
                raise
            finally:
                _record_duration(
                    duration_histogram,
                    timeit.default_timer() - start,
                    "delete_memory",
                    error_type,
                )

            return result

    return wrapper


def wrap_memory_delete_all(
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(
        _INSTRUMENTATION_NAME, tracer_provider=tracer_provider
    )
    meter = get_meter(_INSTRUMENTATION_NAME, meter_provider=meter_provider)
    duration_histogram = create_duration_histogram(meter)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        span_name = f"delete_memory {_PROVIDER}"
        error_type = None
        start = timeit.default_timer()
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "delete_memory", kwargs)

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                error_type = _set_error(span, exc)
                raise
            finally:
                _record_duration(
                    duration_histogram,
                    timeit.default_timer() - start,
                    "delete_memory",
                    error_type,
                )

            return result

    return wrapper


def wrap_memory_get_all(
    tracer_provider: Optional[trace.TracerProvider] = None,
    meter_provider: Optional[MeterProvider] = None,
) -> Callable:
    tracer = trace.get_tracer(
        _INSTRUMENTATION_NAME, tracer_provider=tracer_provider
    )
    meter = get_meter(_INSTRUMENTATION_NAME, meter_provider=meter_provider)
    duration_histogram = create_duration_histogram(meter)

    def wrapper(
        wrapped: Callable, instance: Any, args: Any, kwargs: Any
    ) -> Any:
        span_name = f"search_memory {_PROVIDER}"
        error_type = None
        start = timeit.default_timer()
        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT
        ) as span:
            _set_common_attributes(span, "search_memory", kwargs)

            try:
                result = wrapped(*args, **kwargs)
            except Exception as exc:
                error_type = _set_error(span, exc)
                raise
            finally:
                _record_duration(
                    duration_histogram,
                    timeit.default_timer() - start,
                    "search_memory",
                    error_type,
                )

            count = _result_count(result)
            if count is not None:
                span.set_attribute(GEN_AI_MEMORY_SEARCH_RESULT_COUNT, count)

            return result

    return wrapper
