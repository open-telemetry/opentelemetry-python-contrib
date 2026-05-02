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
Instrument uncaught exceptions to emit OpenTelemetry logs.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.exceptions import (
        UnhandledExceptionInstrumentor,
    )

    UnhandledExceptionInstrumentor().instrument()

This instrumentation captures uncaught process exceptions, uncaught thread
exceptions, and unhandled asyncio task exceptions and emits them as
OpenTelemetry logs.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Collection
from types import TracebackType
from typing import Any, Callable

from opentelemetry._logs import SeverityNumber, get_logger
from opentelemetry.instrumentation.exceptions.package import _instruments
from opentelemetry.instrumentation.exceptions.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv.schemas import Schemas


class _ExceptionLogger:
    def __init__(self, logger_provider: Any = None):
        self._logger = get_logger(
            __name__,
            __version__,
            logger_provider,
            schema_url=Schemas.V1_37_0.value,
        )

    def emit(
        self,
        exc: Exception,
        *,
        severity_text: str,
        severity_number: SeverityNumber,
    ) -> None:
        self._logger.emit(
            body=str(exc),
            severity_text=severity_text,
            severity_number=severity_number,
            exception=exc,
        )


class UnhandledExceptionInstrumentor(BaseInstrumentor):
    """Emit logs for uncaught exceptions and unhandled asyncio exceptions."""

    def __init__(self, logger_provider: Any = None):
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

        def _handle_sys_exc(
            exc_type: type[BaseException],
            exc: BaseException,
            tb: TracebackType | None,
        ) -> None:
            if isinstance(exc, Exception) and self._exception_logger is not None:
                try:
                    self._exception_logger.emit(
                        exc,
                        severity_text="FATAL",
                        severity_number=SeverityNumber.FATAL,
                    )
                except Exception:  # pragma: no cover  # pylint: disable=broad-exception-caught
                    pass
            self._original_sys_excepthook(exc_type, exc, tb)

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
        if self._original_threading_excepthook is not None:
            return

        self._original_threading_excepthook = threading.excepthook

        def _handle_threading_exc(args: threading.ExceptHookArgs) -> None:
            if (
                isinstance(args.exc_value, Exception)
                and self._exception_logger is not None
            ):
                try:
                    self._exception_logger.emit(
                        args.exc_value,
                        severity_text="ERROR",
                        severity_number=SeverityNumber.ERROR,
                    )
                except Exception:  # pragma: no cover  # pylint: disable=broad-exception-caught
                    pass
            self._original_threading_excepthook(args)

        self._threading_excepthook = _handle_threading_exc
        threading.excepthook = _handle_threading_exc

    def _restore_threading_hook(self) -> None:
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

        self._original_asyncio_call_exception_handler = (
            asyncio.BaseEventLoop.call_exception_handler
        )

        def _call_exception_handler(
            loop: asyncio.AbstractEventLoop,
            context: dict[str, Any],
        ) -> None:
            exc = context.get("exception")
            if isinstance(exc, Exception) and self._exception_logger is not None:
                try:
                    self._exception_logger.emit(
                        exc,
                        severity_text="ERROR",
                        severity_number=SeverityNumber.ERROR,
                    )
                except Exception:  # pragma: no cover  # pylint: disable=broad-exception-caught
                    pass
            self._original_asyncio_call_exception_handler(loop, context)

        self._asyncio_call_exception_handler = _call_exception_handler
        asyncio.BaseEventLoop.call_exception_handler = _call_exception_handler

    def _restore_asyncio_hook(self) -> None:
        if (
            self._original_asyncio_call_exception_handler is not None
            and asyncio.BaseEventLoop.call_exception_handler
            is self._asyncio_call_exception_handler
        ):
            asyncio.BaseEventLoop.call_exception_handler = (
                self._original_asyncio_call_exception_handler
            )
        self._original_asyncio_call_exception_handler = None
        self._asyncio_call_exception_handler = None


__all__ = ["UnhandledExceptionInstrumentor"]
