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
#
"""
Shared instrumentation base for Redis and Valkey.

This module provides parameterized factory functions and utilities used by
both ``opentelemetry-instrumentation-redis`` and
``opentelemetry-instrumentation-valkey``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from opentelemetry import trace
from opentelemetry.instrumentation._redis_valkey.util import (
    _add_create_attributes,
    _add_search_attributes,
    _build_span_meta_data_for_pipeline,
    _build_span_name,
    _format_command_args,
    _set_connection_attributes,
)
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_STATEMENT,
)
from opentelemetry.trace import StatusCode, Tracer


@dataclass(frozen=True)
class KVStoreConfig:
    """Configuration for a key-value store backend (Redis or Valkey).

    All backend-specific differences are captured here so that the shared
    factory functions can be used by both Redis and Valkey instrumentations.
    """

    # Identity
    backend_name: str  # "redis" or "valkey"
    db_system: str  # "redis" or "valkey"

    # Span attribute keys
    db_system_attr: str  # DB_SYSTEM semconv key
    db_index_attr: str  # DB_REDIS_DATABASE_INDEX or "db.valkey.database_index"
    args_length_attr: str  # "db.redis.args_length" or "db.valkey.args_length"
    pipeline_length_attr: str  # "db.redis.pipeline_length" or "db.valkey.pipeline_length"

    # WatchError class from the backend library
    watch_error_class: type


def _traced_execute_factory(
    config: KVStoreConfig,
    tracer: Tracer,
    request_hook: Callable | None = None,
    response_hook: Callable | None = None,
):
    """Create a wrapper for execute_command that creates spans."""

    def _traced_execute_command(func, instance, args, kwargs):
        if not is_instrumentation_enabled():
            return func(*args, **kwargs)

        query = _format_command_args(args)
        name = _build_span_name(instance, args, config.backend_name)
        with tracer.start_as_current_span(
            name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span.set_attribute(DB_STATEMENT, query)
                _set_connection_attributes(
                    span,
                    instance,
                    config.db_system,
                    config.db_system_attr,
                    config.db_index_attr,
                )
                span.set_attribute(config.args_length_attr, len(args))
                if span.name == f"{config.backend_name}.create_index":
                    _add_create_attributes(
                        span, args, config.backend_name
                    )
            if callable(request_hook):
                request_hook(span, instance, args, kwargs)
            response = func(*args, **kwargs)
            if span.is_recording():
                if span.name == f"{config.backend_name}.search":
                    _add_search_attributes(
                        span, response, args, config.backend_name
                    )
            if callable(response_hook):
                response_hook(span, instance, response)
            return response

    return _traced_execute_command


def _traced_execute_pipeline_factory(
    config: KVStoreConfig,
    tracer: Tracer,
    request_hook: Callable | None = None,
    response_hook: Callable | None = None,
):
    """Create a wrapper for pipeline execute that creates spans."""

    def _traced_execute_pipeline(func, instance, args, kwargs):
        if not is_instrumentation_enabled():
            return func(*args, **kwargs)

        (
            command_stack,
            resource,
            span_name,
        ) = _build_span_meta_data_for_pipeline(instance, config.backend_name)
        exception = None
        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span.set_attribute(DB_STATEMENT, resource)
                _set_connection_attributes(
                    span,
                    instance,
                    config.db_system,
                    config.db_system_attr,
                    config.db_index_attr,
                )
                span.set_attribute(
                    config.pipeline_length_attr, len(command_stack)
                )

            response = None
            try:
                response = func(*args, **kwargs)
            except config.watch_error_class as watch_exception:
                span.set_status(StatusCode.UNSET)
                exception = watch_exception

            if callable(response_hook):
                response_hook(span, instance, response)

        if exception:
            raise exception

        return response

    return _traced_execute_pipeline


def _async_traced_execute_factory(
    config: KVStoreConfig,
    tracer: Tracer,
    request_hook: Callable | None = None,
    response_hook: Callable | None = None,
):
    """Create an async wrapper for execute_command that creates spans."""

    async def _async_traced_execute_command(func, instance, args, kwargs):
        if not is_instrumentation_enabled():
            return await func(*args, **kwargs)

        query = _format_command_args(args)
        name = _build_span_name(instance, args, config.backend_name)

        with tracer.start_as_current_span(
            name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span.set_attribute(DB_STATEMENT, query)
                _set_connection_attributes(
                    span,
                    instance,
                    config.db_system,
                    config.db_system_attr,
                    config.db_index_attr,
                )
                span.set_attribute(config.args_length_attr, len(args))
            if callable(request_hook):
                request_hook(span, instance, args, kwargs)
            response = await func(*args, **kwargs)
            if callable(response_hook):
                response_hook(span, instance, response)
            return response

    return _async_traced_execute_command


def _async_traced_execute_pipeline_factory(
    config: KVStoreConfig,
    tracer: Tracer,
    request_hook: Callable | None = None,
    response_hook: Callable | None = None,
):
    """Create an async wrapper for pipeline execute that creates spans."""

    async def _async_traced_execute_pipeline(func, instance, args, kwargs):
        if not is_instrumentation_enabled():
            return await func(*args, **kwargs)

        (
            command_stack,
            resource,
            span_name,
        ) = _build_span_meta_data_for_pipeline(instance, config.backend_name)

        exception = None

        with tracer.start_as_current_span(
            span_name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span.set_attribute(DB_STATEMENT, resource)
                _set_connection_attributes(
                    span,
                    instance,
                    config.db_system,
                    config.db_system_attr,
                    config.db_index_attr,
                )
                span.set_attribute(
                    config.pipeline_length_attr, len(command_stack)
                )

            response = None
            try:
                response = await func(*args, **kwargs)
            except config.watch_error_class as watch_exception:
                span.set_status(StatusCode.UNSET)
                exception = watch_exception

            if callable(response_hook):
                response_hook(span, instance, response)

        if exception:
            raise exception

        return response

    return _async_traced_execute_pipeline
