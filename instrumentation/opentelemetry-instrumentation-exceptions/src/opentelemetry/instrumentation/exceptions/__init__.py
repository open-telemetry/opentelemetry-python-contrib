# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
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

from opentelemetry._logs import Logger, SeverityNumber, get_logger
from opentelemetry.instrumentation.exceptions.package import _instruments
from opentelemetry.instrumentation.exceptions.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas


class UnhandledExceptionInstrumentor(BaseInstrumentor):
    """Emit logs for uncaught exceptions and unhandled asyncio exceptions."""

    def __init__(self):
        super().__init__()
        self._logger: Logger | None = None

    # pylint: disable-next=no-self-use
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        self._logger = get_logger(
            __name__,
            __version__,
            kwargs.get("logger_provider"),
            schema_url=Schemas.V1_37_0.value,
        )
        self._install_sys_hook()
        self._install_threading_hook()
        self._install_asyncio_hook()

    def _uninstrument(self, **kwargs: Any):
        self._restore_sys_hook()
        self._restore_threading_hook()
        self._restore_asyncio_hook()
        self._logger = None

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
        event_name: str,
    ) -> None:
        # BaseException includes process-control signals like KeyboardInterrupt.
        if not isinstance(exc, Exception) or self._logger is None:
            return

        try:
            self._logger.emit(
                event_name=event_name,
                body=str(exc),
                severity_text=severity_text,
                severity_number=severity_number,
                exception=exc,
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
            event_name=type(exc).__name__,
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
            event_name=hook_args.exc_type.__name__,
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
            message = context.get("message")
            self._emit_exception(
                exc,
                severity_text="ERROR",
                severity_number=SeverityNumber.ERROR,
                event_name=str(message) if message else type(exc).__name__,
            )
        wrapped(*args, **kwargs)


__all__ = ["UnhandledExceptionInstrumentor"]
