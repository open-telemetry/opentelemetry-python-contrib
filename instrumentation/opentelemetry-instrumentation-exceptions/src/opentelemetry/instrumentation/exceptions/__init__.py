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
from typing import Any

from wrapt import (
    wrap_function_wrapper,  # type: ignore[reportUnknownVariableType]
)

from opentelemetry._logs import LoggerProvider, SeverityNumber, get_logger
from opentelemetry.instrumentation.exceptions.package import _instruments
from opentelemetry.instrumentation.exceptions.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas


class _ExceptionLogger:
    def __init__(self, logger_provider: LoggerProvider | None = None):
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

    def __init__(self, logger_provider: LoggerProvider | None = None):
        super().__init__()
        self._logger_provider = logger_provider
        self._exception_logger: _ExceptionLogger | None = None

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
        wrap_function_wrapper(
            sys,
            "excepthook",
            self._wrap_sys_excepthook,
        )

    @staticmethod
    def _restore_sys_hook() -> None:
        unwrap(sys, "excepthook")

    def _install_threading_hook(self) -> None:
        wrap_function_wrapper(
            threading,
            "excepthook",
            self._wrap_threading_excepthook,
        )

    @staticmethod
    def _restore_threading_hook() -> None:
        unwrap(threading, "excepthook")

    def _install_asyncio_hook(self) -> None:
        wrap_function_wrapper(
            asyncio.BaseEventLoop,
            "call_exception_handler",
            self._wrap_asyncio_call_exception_handler,
        )

    @staticmethod
    def _restore_asyncio_hook() -> None:
        unwrap(asyncio.BaseEventLoop, "call_exception_handler")

    def _emit_exception(
        self,
        exc: BaseException,
        *,
        severity_text: str,
        severity_number: SeverityNumber,
    ) -> None:
        if not isinstance(exc, Exception) or self._exception_logger is None:
            return

        try:
            self._exception_logger.emit(
                exc,
                severity_text=severity_text,
                severity_number=severity_number,
            )
        # Logging must never replace the original unhandled exception path.
        # pylint: disable-next=broad-exception-caught
        except Exception:  # pragma: no cover
            pass

    def _wrap_sys_excepthook(
        self,
        wrapped,
        instance,
        args: tuple[type[BaseException], BaseException, TracebackType | None],
        kwargs: dict[str, Any],
    ) -> None:
        _, exc, _ = args
        self._emit_exception(
            exc,
            severity_text="FATAL",
            severity_number=SeverityNumber.FATAL,
        )
        wrapped(*args, **kwargs)

    def _wrap_threading_excepthook(
        self,
        wrapped,
        instance,
        args: tuple[threading.ExceptHookArgs],
        kwargs: dict[str, Any],
    ) -> None:
        (hook_args,) = args
        self._emit_exception(
            hook_args.exc_value,
            severity_text="ERROR",
            severity_number=SeverityNumber.ERROR,
        )
        wrapped(*args, **kwargs)

    def _wrap_asyncio_call_exception_handler(
        self,
        wrapped,
        instance: asyncio.AbstractEventLoop,
        args: tuple[dict[str, Any]],
        kwargs: dict[str, Any],
    ) -> None:
        (context,) = args
        exc = context.get("exception")
        if isinstance(exc, BaseException):
            self._emit_exception(
                exc,
                severity_text="ERROR",
                severity_number=SeverityNumber.ERROR,
            )
        wrapped(*args, **kwargs)


__all__ = ["UnhandledExceptionInstrumentor"]
