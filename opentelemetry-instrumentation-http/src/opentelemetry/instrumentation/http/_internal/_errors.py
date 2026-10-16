# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio

from opentelemetry.semconv.attributes.error_attributes import ErrorTypeValues

_OTHER_ERROR_TYPE = ErrorTypeValues.OTHER.value
_BUILTINS_MODULE = "builtins"
_CANCELLATION_TYPES = (asyncio.CancelledError, GeneratorExit, KeyboardInterrupt)


def is_error_status_code(status_code: int) -> bool:
    """Return whether an HTTP client response status code indicates an error."""
    return status_code >= 400 or status_code < 100


def get_exception_type(exception: BaseException) -> str:
    """Return the fully qualified type name of ``exception``, without the ``builtins`` module."""
    exception_type = type(exception)
    if exception_type.__module__ == _BUILTINS_MODULE:
        return exception_type.__qualname__
    return f"{exception_type.__module__}.{exception_type.__qualname__}"


def is_cancellation(exception: BaseException | None) -> bool:
    """Return whether ``exception`` indicates that the caller cancelled the request."""
    return isinstance(exception, _CANCELLATION_TYPES)


def get_error_type(status_code: int | None, error_type: str | None, exception: BaseException | None) -> str | None:
    """Return ``error.type`` for a request, or ``None`` if it did not end with an error.

    An error status code takes precedence, then ``error_type``, then the type of
    ``exception``. An empty ``error_type`` is recorded as ``_OTHER``.
    """
    if status_code is not None and is_error_status_code(status_code):
        return str(status_code)
    if error_type is not None:
        return error_type or _OTHER_ERROR_TYPE
    if exception is not None:
        return get_exception_type(exception)
    return None
