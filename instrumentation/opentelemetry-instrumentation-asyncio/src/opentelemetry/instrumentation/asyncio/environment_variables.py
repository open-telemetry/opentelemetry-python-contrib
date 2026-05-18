# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
.. envvar:: OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE

    Enter the names of the coroutines to be traced through the environment variable below, separated by commas.

.. envvar:: OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED

    To determine whether the tracing feature for Future of Asyncio in Python is enabled or not.

.. envvar:: OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE

    Enter the names of the functions to be traced through the environment variable below, separated by commas.
"""

OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE = (
    "OTEL_PYTHON_ASYNCIO_COROUTINE_NAMES_TO_TRACE"
)

OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED = (
    "OTEL_PYTHON_ASYNCIO_FUTURE_TRACE_ENABLED"
)

OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE = (
    "OTEL_PYTHON_ASYNCIO_TO_THREAD_FUNCTION_NAMES_TO_TRACE"
)
