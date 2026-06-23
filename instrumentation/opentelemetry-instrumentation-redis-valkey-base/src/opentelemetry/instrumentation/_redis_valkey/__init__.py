# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
#
"""
Shared instrumentation base for Redis and Valkey.

This module provides parameterized factory functions and utilities used by
both ``opentelemetry-instrumentation-redis`` and
``opentelemetry-instrumentation-valkey``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from opentelemetry import trace
from opentelemetry.instrumentation._redis_valkey.util import (
    _add_create_attributes,
    _add_search_attributes,
    _build_span_meta_data_for_pipeline,
    _build_span_name,
    _format_command_args,
    _set_connection_attributes,
)
from opentelemetry.instrumentation._semconv import (
    _get_semconv_opt_in_modes,
    _OpenTelemetryStabilitySignalType,
    _set_db_statement,
)
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
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

    # WatchError class from the backend library
    watch_error_class: type


def _get_db_and_http_modes():
    sem_conv_opt_in_modes = _get_semconv_opt_in_modes(
        (
            _OpenTelemetryStabilitySignalType.DATABASE,
            _OpenTelemetryStabilitySignalType.HTTP,
        )
    )
    return (
        sem_conv_opt_in_modes[_OpenTelemetryStabilitySignalType.DATABASE],
        sem_conv_opt_in_modes[_OpenTelemetryStabilitySignalType.HTTP],
    )


def _traced_execute_factory(
    config: KVStoreConfig,
    tracer: Tracer,
    request_hook: Callable | None = None,
    response_hook: Callable | None = None,
):
    """Create a wrapper for execute_command that creates spans."""
    db_sem_conv_opt_in_mode, http_sem_conv_opt_in_mode = (
        _get_db_and_http_modes()
    )

    def _traced_execute_command(func, instance, args, kwargs):
        if not is_instrumentation_enabled():
            return func(*args, **kwargs)

        query = _format_command_args(args)
        name = _build_span_name(instance, args, config.backend_name)
        with tracer.start_as_current_span(
            name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span_attrs: dict = {}
                _set_db_statement(span_attrs, query, db_sem_conv_opt_in_mode)
                span_attrs[f"db.{config.backend_name}.args_length"] = len(args)
                for key, value in span_attrs.items():
                    span.set_attribute(key, value)
                _set_connection_attributes(
                    span,
                    instance,
                    config.db_system,
                    db_sem_conv_opt_in_mode,
                    http_sem_conv_opt_in_mode,
                )
                if span.name == f"{config.backend_name}.create_index":
                    _add_create_attributes(span, args, config.backend_name)
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
    db_sem_conv_opt_in_mode, http_sem_conv_opt_in_mode = (
        _get_db_and_http_modes()
    )

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
                span_attrs: dict = {}
                _set_db_statement(
                    span_attrs, resource, db_sem_conv_opt_in_mode
                )
                span_attrs[f"db.{config.backend_name}.pipeline_length"] = len(
                    command_stack
                )
                for key, value in span_attrs.items():
                    span.set_attribute(key, value)
                _set_connection_attributes(
                    span,
                    instance,
                    config.db_system,
                    db_sem_conv_opt_in_mode,
                    http_sem_conv_opt_in_mode,
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
    db_sem_conv_opt_in_mode, http_sem_conv_opt_in_mode = (
        _get_db_and_http_modes()
    )

    async def _async_traced_execute_command(func, instance, args, kwargs):
        if not is_instrumentation_enabled():
            return await func(*args, **kwargs)

        query = _format_command_args(args)
        name = _build_span_name(instance, args, config.backend_name)

        with tracer.start_as_current_span(
            name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                span_attrs: dict = {}
                _set_db_statement(span_attrs, query, db_sem_conv_opt_in_mode)
                span_attrs[f"db.{config.backend_name}.args_length"] = len(args)
                for key, value in span_attrs.items():
                    span.set_attribute(key, value)
                _set_connection_attributes(
                    span,
                    instance,
                    config.db_system,
                    db_sem_conv_opt_in_mode,
                    http_sem_conv_opt_in_mode,
                )
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
    db_sem_conv_opt_in_mode, http_sem_conv_opt_in_mode = (
        _get_db_and_http_modes()
    )

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
                span_attrs: dict = {}
                _set_db_statement(
                    span_attrs, resource, db_sem_conv_opt_in_mode
                )
                span_attrs[f"db.{config.backend_name}.pipeline_length"] = len(
                    command_stack
                )
                for key, value in span_attrs.items():
                    span.set_attribute(key, value)
                _set_connection_attributes(
                    span,
                    instance,
                    config.db_system,
                    db_sem_conv_opt_in_mode,
                    http_sem_conv_opt_in_mode,
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
