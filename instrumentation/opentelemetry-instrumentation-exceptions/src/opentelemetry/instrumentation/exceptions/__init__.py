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
"""
Emit OpenTelemetry log records for unhandled exceptions.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.exceptions import (
        UnhandledExceptionInstrumentor,
    )

    UnhandledExceptionInstrumentor().instrument()
"""

from __future__ import annotations

import asyncio
import sys
import threading
import traceback
from typing import Any, Callable, Collection

from opentelemetry._logs import LogRecord, get_logger
from opentelemetry.context import get_current
from opentelemetry.instrumentation.exceptions.package import _instruments
from opentelemetry.instrumentation.exceptions.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv.attributes import exception_attributes
from opentelemetry.semconv.schemas import Schemas

try:  # pragma: no cover - optional API for older SDKs
    from opentelemetry._logs import SeverityNumber
except ImportError:  # pragma: no cover - older SDKs don't expose this
    SeverityNumber = None


def _format_stacktrace(
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: Any,
) -> str | None:
    if exc_type is None and exc is not None:
        exc_type = type(exc)
    if tb is None and exc is not None:
        tb = exc.__traceback__
    if exc_type is None:
        return None
    return "".join(traceback.format_exception(exc_type, exc, tb))


def _exception_attributes(
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    tb: Any,
) -> dict[str, str]:
    attributes: dict[str, str] = {}
    if exc_type is None and exc is not None:
        exc_type = type(exc)
    if exc_type is not None:
        attributes[exception_attributes.EXCEPTION_TYPE] = exc_type.__name__
    if exc is not None:
        attributes[exception_attributes.EXCEPTION_MESSAGE] = str(exc)
    stacktrace = _format_stacktrace(exc_type, exc, tb)
    if stacktrace:
        attributes[exception_attributes.EXCEPTION_STACKTRACE] = stacktrace
    return attributes


def _severity_number(severity_text: str) -> Any:
    if SeverityNumber is None:
        return None
    if severity_text == "FATAL":
        return SeverityNumber.FATAL
    if severity_text == "ERROR":
        return SeverityNumber.ERROR
    return None


class _ExceptionLogger:
    def __init__(self, logger_provider=None):
        self._logger = get_logger(
            __name__,
            __version__,
            logger_provider,
            schema_url=Schemas.V1_37_0.value,
        )

    def emit(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
        severity_text: str,
    ) -> None:
        attributes = _exception_attributes(exc_type, exc, tb)
        log_record = LogRecord(
            attributes=attributes or None,
            body=str(exc) if exc is not None else None,
            severity_text=severity_text,
            severity_number=_severity_number(severity_text),
            context=get_current(),
        )
        self._logger.emit(log_record)


class UnhandledExceptionInstrumentor(BaseInstrumentor):
    """Emit logs for uncaught exceptions and unhandled asyncio exceptions."""

    def __init__(self, logger_provider=None):
        super().__init__()
        self._logger_provider = logger_provider
        self._exception_logger: _ExceptionLogger | None = None
        self._original_sys_excepthook: Callable[..., Any] | None = None
        self._original_threading_excepthook: Callable[..., Any] | None = None
        self._original_asyncio_call_exception_handler: (
            Callable[..., Any] | None
        ) = None
        self._sys_excepthook: Callable[..., Any] | None = None
        self._threading_excepthook: Callable[..., Any] | None = None
        self._asyncio_call_exception_handler: Callable[..., Any] | None = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        logger_provider = kwargs.get("logger_provider", self._logger_provider)
        self._exception_logger = _ExceptionLogger(logger_provider)
        self._install_sys_hook()
        self._install_threading_hook()
        self._install_asyncio_hook()

    def _uninstrument(self, **kwargs: Any):
        self._restore_sys_hook()
        self._restore_threading_hook()
        self._restore_asyncio_hook()
        self._exception_logger = None

    def _install_sys_hook(self) -> None:
        if self._original_sys_excepthook is not None:
            return

        self._original_sys_excepthook = sys.excepthook

        def _handle_sys_exc(exc_type, exc, tb):
            if self._exception_logger is not None:
                try:
                    self._exception_logger.emit(exc_type, exc, tb, "FATAL")
                except Exception:  # pragma: no cover - defensive  # pylint: disable=broad-exception-caught
                    pass
            return self._original_sys_excepthook(exc_type, exc, tb)

        self._sys_excepthook = _handle_sys_exc
        sys.excepthook = _handle_sys_exc

    def _restore_sys_hook(self) -> None:
        if (
            self._original_sys_excepthook is not None
            and sys.excepthook is self._sys_excepthook
        ):
            sys.excepthook = self._original_sys_excepthook
        self._original_sys_excepthook = None
        self._sys_excepthook = None

    def _install_threading_hook(self) -> None:
        if not hasattr(threading, "excepthook"):
            return
        if self._original_threading_excepthook is not None:
            return

        self._original_threading_excepthook = threading.excepthook

        def _handle_threading_exc(args):
            if self._exception_logger is not None:
                try:
                    self._exception_logger.emit(
                        args.exc_type,
                        args.exc_value,
                        args.exc_traceback,
                        "ERROR",
                    )
                except Exception:  # pragma: no cover - defensive  # pylint: disable=broad-exception-caught
                    pass
            return self._original_threading_excepthook(args)

        self._threading_excepthook = _handle_threading_exc
        threading.excepthook = _handle_threading_exc

    def _restore_threading_hook(self) -> None:
        if not hasattr(threading, "excepthook"):
            return
        if (
            self._original_threading_excepthook is not None
            and threading.excepthook is self._threading_excepthook
        ):
            threading.excepthook = self._original_threading_excepthook
        self._original_threading_excepthook = None
        self._threading_excepthook = None

    def _install_asyncio_hook(self) -> None:
        if self._original_asyncio_call_exception_handler is not None:
            return
        base_loop = getattr(asyncio, "BaseEventLoop", None)
        if base_loop is None:
            return

        self._original_asyncio_call_exception_handler = (
            base_loop.call_exception_handler
        )

        def _call_exception_handler(loop, context):
            exc = context.get("exception") if context else None
            if exc is not None and self._exception_logger is not None:
                try:
                    self._exception_logger.emit(
                        type(exc), exc, exc.__traceback__, "ERROR"
                    )
                except Exception:  # pragma: no cover - defensive  # pylint: disable=broad-exception-caught
                    pass
            return self._original_asyncio_call_exception_handler(loop, context)

        self._asyncio_call_exception_handler = _call_exception_handler
        base_loop.call_exception_handler = _call_exception_handler

    def _restore_asyncio_hook(self) -> None:
        base_loop = getattr(asyncio, "BaseEventLoop", None)
        if base_loop is None:
            return
        if (
            self._original_asyncio_call_exception_handler is not None
            and base_loop.call_exception_handler
            is self._asyncio_call_exception_handler
        ):
            base_loop.call_exception_handler = (
                self._original_asyncio_call_exception_handler
            )
        self._original_asyncio_call_exception_handler = None
        self._asyncio_call_exception_handler = None


__all__ = ["UnhandledExceptionInstrumentor"]
