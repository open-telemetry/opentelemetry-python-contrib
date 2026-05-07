# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import os
from typing import Set

# pylint: disable=no-name-in-module
from opentelemetry.instrumentation.asyncio.environment_variables import (
    OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE,
    OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED,
    OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE,
)


def separate_coro_names_by_comma(coro_names: str) -> Set[str]:
    """
    Function to separate the coroutines to be traced by comma
    """
    if coro_names is None:
        return set()
    return {coro_name.strip() for coro_name in coro_names.split(",")}


def get_coros_to_trace() -> set:
    """
    Function to get the coroutines to be traced from the environment variable
    """
    coro_names = os.getenv(OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE)
    return separate_coro_names_by_comma(coro_names)


def get_future_trace_enabled() -> bool:
    """
    Function to get the future active enabled flag from the environment variable
    default value is False
    """
    return (
        os.getenv(OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED, "False").lower()
        == "true"
    )


def get_to_thread_to_trace() -> set:
    """
    Function to get the functions to be traced from the environment variable
    """
    func_names = os.getenv(
        OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE
    )
    return separate_coro_names_by_comma(func_names)


__all__ = [
    "get_coros_to_trace",
    "get_future_trace_enabled",
    "get_to_thread_to_trace",
]
