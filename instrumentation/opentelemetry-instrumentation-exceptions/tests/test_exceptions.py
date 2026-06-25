# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Generator

import pytest

import opentelemetry._logs._internal
from opentelemetry._logs import (
    SeverityNumber,
    get_logger_provider,
    set_logger_provider,
)
from opentelemetry.instrumentation.exceptions import (
    UnhandledExceptionInstrumentor,
)
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.semconv.attributes import exception_attributes
from opentelemetry.util._once import Once

# pylint: disable=redefined-outer-name


@pytest.fixture
def log_exporter() -> Generator[InMemoryLogRecordExporter, None, None]:
    snapshot = get_logger_provider()
    opentelemetry._logs._internal._LOGGER_PROVIDER_SET_ONCE = Once()
    provider = LoggerProvider()
    exporter = InMemoryLogRecordExporter()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    set_logger_provider(provider)
    try:
        yield exporter
    finally:
        opentelemetry._logs._internal._LOGGER_PROVIDER_SET_ONCE = Once()
        set_logger_provider(snapshot)


@pytest.fixture
def instrumentor() -> Generator[UnhandledExceptionInstrumentor, None, None]:
    inst = UnhandledExceptionInstrumentor()
    try:
        yield inst
    finally:
        inst.uninstrument()


def _raised_value_error() -> ValueError:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return exc


def _finished_log(log_exporter: InMemoryLogRecordExporter):
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    return logs[0].log_record


def test_sys_excepthook_emits_log(
    log_exporter: InMemoryLogRecordExporter,
    monkeypatch: pytest.MonkeyPatch,
    instrumentor: UnhandledExceptionInstrumentor,
) -> None:
    called = {"value": False}

    def stub_excepthook(exc_type, exc, tb) -> None:
        called["value"] = True

    monkeypatch.setattr(sys, "excepthook", stub_excepthook)
    instrumentor.instrument()

    exc = _raised_value_error()
    sys.excepthook(type(exc), exc, exc.__traceback__)

    log_record = _finished_log(log_exporter)
    assert log_record.severity_text == "FATAL"
    assert log_record.severity_number == SeverityNumber.FATAL
    assert log_record.event_name == "ValueError"
    assert log_record.body == "boom"
    assert called["value"] is True

    attributes = log_record.attributes
    assert attributes[exception_attributes.EXCEPTION_TYPE] == "ValueError"
    assert isinstance(attributes[exception_attributes.EXCEPTION_TYPE], str)
    assert attributes[exception_attributes.EXCEPTION_MESSAGE] == "boom"
    assert isinstance(attributes[exception_attributes.EXCEPTION_MESSAGE], str)
    assert "ValueError: boom" in attributes[exception_attributes.EXCEPTION_STACKTRACE]
    assert isinstance(attributes[exception_attributes.EXCEPTION_STACKTRACE], str)


def test_threading_excepthook_emits_log(
    log_exporter: InMemoryLogRecordExporter,
    monkeypatch: pytest.MonkeyPatch,
    instrumentor: UnhandledExceptionInstrumentor,
) -> None:
    called = {"value": False}

    def stub_threading_excepthook(args: threading.ExceptHookArgs) -> None:
        called["value"] = True

    monkeypatch.setattr(threading, "excepthook", stub_threading_excepthook)
    instrumentor.instrument()

    exc = _raised_value_error()
    args = threading.ExceptHookArgs((type(exc), exc, exc.__traceback__, threading.current_thread()))
    threading.excepthook(args)

    log_record = _finished_log(log_exporter)
    assert log_record.severity_text == "ERROR"
    assert log_record.severity_number == SeverityNumber.ERROR
    assert log_record.event_name == "ValueError"
    assert log_record.body == "boom"
    assert called["value"] is True

    attributes = log_record.attributes
    assert attributes[exception_attributes.EXCEPTION_TYPE] == "ValueError"
    assert attributes[exception_attributes.EXCEPTION_MESSAGE] == "boom"
    assert "ValueError: boom" in attributes[exception_attributes.EXCEPTION_STACKTRACE]


def test_asyncio_unhandled_exception_emits_log(
    log_exporter: InMemoryLogRecordExporter,
    monkeypatch: pytest.MonkeyPatch,
    instrumentor: UnhandledExceptionInstrumentor,
) -> None:
    called = {"value": False}

    original_handler = asyncio.BaseEventLoop.call_exception_handler

    def stub_call_exception_handler(loop, context) -> None:
        called["value"] = True
        original_handler(loop, context)

    monkeypatch.setattr(
        asyncio.BaseEventLoop,
        "call_exception_handler",
        stub_call_exception_handler,
    )
    instrumentor.instrument()

    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda _loop, _context: None)
    try:
        exc = _raised_value_error()
        loop.call_exception_handler({"exception": exc, "message": "task boom"})
    finally:
        loop.close()

    log_record = _finished_log(log_exporter)
    assert log_record.severity_text == "ERROR"
    assert log_record.severity_number == SeverityNumber.ERROR
    assert log_record.event_name == "task boom"
    assert log_record.body == "boom"
    assert called["value"] is True

    attributes = log_record.attributes
    assert attributes[exception_attributes.EXCEPTION_TYPE] == "ValueError"
    assert attributes[exception_attributes.EXCEPTION_MESSAGE] == "boom"
    assert "ValueError: boom" in attributes[exception_attributes.EXCEPTION_STACKTRACE]


def test_asyncio_unhandled_exception_called_with_kwarg_emits_log(
    log_exporter: InMemoryLogRecordExporter,
    monkeypatch: pytest.MonkeyPatch,
    instrumentor: UnhandledExceptionInstrumentor,
) -> None:
    called = {"value": False}

    original_handler = asyncio.BaseEventLoop.call_exception_handler

    def stub_call_exception_handler(loop, context) -> None:
        called["value"] = True
        original_handler(loop, context)

    monkeypatch.setattr(
        asyncio.BaseEventLoop,
        "call_exception_handler",
        stub_call_exception_handler,
    )
    instrumentor.instrument()

    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda _loop, _context: None)
    try:
        exc = _raised_value_error()
        loop.call_exception_handler(context={"exception": exc, "message": "task boom"})
    finally:
        loop.close()

    log_record = _finished_log(log_exporter)
    assert log_record.severity_text == "ERROR"
    assert log_record.severity_number == SeverityNumber.ERROR
    assert log_record.event_name == "task boom"
    assert log_record.body == "boom"
    assert called["value"] is True

    attributes = log_record.attributes
    assert attributes[exception_attributes.EXCEPTION_TYPE] == "ValueError"
    assert attributes[exception_attributes.EXCEPTION_MESSAGE] == "boom"
    assert "ValueError: boom" in attributes[exception_attributes.EXCEPTION_STACKTRACE]


def test_asyncio_unhandled_exception_invalid_call(
    log_exporter: InMemoryLogRecordExporter,
    monkeypatch: pytest.MonkeyPatch,
    instrumentor: UnhandledExceptionInstrumentor,
) -> None:
    called = {"value": False}

    original_handler = asyncio.BaseEventLoop.call_exception_handler

    def stub_call_exception_handler(loop, context) -> None:
        called["value"] = True
        original_handler(loop, context)

    monkeypatch.setattr(
        asyncio.BaseEventLoop,
        "call_exception_handler",
        stub_call_exception_handler,
    )
    instrumentor.instrument()

    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda _loop, _context: None)
    try:
        _raised_value_error()
        with pytest.raises(TypeError):
            loop.call_exception_handler()
    finally:
        loop.close()

    logs = log_exporter.get_finished_logs()
    assert not logs


@pytest.mark.parametrize(
    ("message", "expected_event_name"),
    ((None, "ValueError"), (42, "42")),
)
def test_asyncio_event_name_falls_back_or_coerces(
    log_exporter: InMemoryLogRecordExporter,
    monkeypatch: pytest.MonkeyPatch,
    instrumentor: UnhandledExceptionInstrumentor,
    message: object,
    expected_event_name: str,
) -> None:
    monkeypatch.setattr(
        asyncio.BaseEventLoop,
        "call_exception_handler",
        lambda _loop, _context: None,
    )
    instrumentor.instrument()

    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda _loop, _context: None)
    try:
        exc = _raised_value_error()
        loop.call_exception_handler({"exception": exc, "message": message})
    finally:
        loop.close()

    assert _finished_log(log_exporter).event_name == expected_event_name


def test_base_exceptions_are_not_emitted(
    log_exporter: InMemoryLogRecordExporter,
    monkeypatch: pytest.MonkeyPatch,
    instrumentor: UnhandledExceptionInstrumentor,
) -> None:
    called = {"value": False}

    def stub_excepthook(exc_type, exc, tb) -> None:
        called["value"] = True

    monkeypatch.setattr(sys, "excepthook", stub_excepthook)
    instrumentor.instrument()

    exc = KeyboardInterrupt()
    sys.excepthook(type(exc), exc, exc.__traceback__)

    assert not log_exporter.get_finished_logs()
    assert called["value"] is True


def test_double_instrument_does_not_emit_duplicate_logs(
    log_exporter: InMemoryLogRecordExporter,
    monkeypatch: pytest.MonkeyPatch,
    instrumentor: UnhandledExceptionInstrumentor,
) -> None:
    monkeypatch.setattr(sys, "excepthook", lambda _exc_type, _exc, _tb: None)

    instrumentor.instrument()
    instrumentor.instrument()

    exc = _raised_value_error()
    sys.excepthook(type(exc), exc, exc.__traceback__)

    assert len(log_exporter.get_finished_logs()) == 1


def test_uninstrument_restores_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instrumentor = UnhandledExceptionInstrumentor()

    def original_sys(exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def original_threading(args: threading.ExceptHookArgs) -> None:
        del args

    def original_asyncio(loop, context) -> None:
        del loop, context

    monkeypatch.setattr(sys, "excepthook", original_sys)
    monkeypatch.setattr(threading, "excepthook", original_threading)
    monkeypatch.setattr(
        asyncio.BaseEventLoop,
        "call_exception_handler",
        original_asyncio,
    )

    instrumentor.instrument(logger_provider=LoggerProvider())
    instrumentor.uninstrument()

    assert sys.excepthook is original_sys
    assert threading.excepthook is original_threading
    assert asyncio.BaseEventLoop.call_exception_handler is original_asyncio
