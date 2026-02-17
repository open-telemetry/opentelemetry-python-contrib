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

import asyncio
import sys
import threading

import pytest

import opentelemetry._logs._internal
from opentelemetry._logs import get_logger_provider, set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider

# Backward compatibility for InMemoryLogExporter -> InMemoryLogRecordExporter
try:
    from opentelemetry.sdk._logs.export import (  # pylint: disable=no-name-in-module
        InMemoryLogRecordExporter,
        SimpleLogRecordProcessor,
    )
except ImportError:
    from opentelemetry.sdk._logs.export import (  # type: ignore
        InMemoryLogExporter as InMemoryLogRecordExporter,
    )
    from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.instrumentation.exceptions import (
    UnhandledExceptionInstrumentor,
    _exception_attributes,
    _format_stacktrace,
    _severity_number,
)
from opentelemetry.semconv.attributes import exception_attributes
from opentelemetry.util._once import Once

# pylint: disable=redefined-outer-name


@pytest.fixture
def log_exporter():
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
def instrumentor():
    inst = UnhandledExceptionInstrumentor()
    try:
        yield inst
    finally:
        inst.uninstrument()


def _raise_value_error():
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return exc, exc.__traceback__


def _get_single_log(log_exporter):
    logs = log_exporter.get_finished_logs()
    assert len(logs) == 1
    return logs[0].log_record


def test_sys_excepthook_emits_log(log_exporter, monkeypatch, instrumentor):
    called = {"value": False}

    def stub_excepthook(exc_type, exc, tb):
        called["value"] = True

    monkeypatch.setattr("sys.excepthook", stub_excepthook)
    instrumentor.instrument()

    exc, tb = _raise_value_error()
    sys.excepthook(type(exc), exc, tb)

    log_record = _get_single_log(log_exporter)
    assert log_record.severity_text == "FATAL"
    attrs = log_record.attributes
    assert attrs[exception_attributes.EXCEPTION_TYPE] == "ValueError"
    assert attrs[exception_attributes.EXCEPTION_MESSAGE] == "boom"
    assert (
        "ValueError: boom" in attrs[exception_attributes.EXCEPTION_STACKTRACE]
    )
    assert called["value"] is True


def test_threading_excepthook_emits_log(
    log_exporter, monkeypatch, instrumentor
):
    called = {"value": False}

    def stub_threading_excepthook(args):
        called["value"] = True

    monkeypatch.setattr("threading.excepthook", stub_threading_excepthook)
    instrumentor.instrument()

    exc, tb = _raise_value_error()
    args = threading.ExceptHookArgs(
        (type(exc), exc, tb, threading.current_thread())
    )
    threading.excepthook(args)

    log_record = _get_single_log(log_exporter)
    assert log_record.severity_text == "ERROR"
    attrs = log_record.attributes
    assert attrs[exception_attributes.EXCEPTION_TYPE] == "ValueError"
    assert attrs[exception_attributes.EXCEPTION_MESSAGE] == "boom"
    assert (
        "ValueError: boom" in attrs[exception_attributes.EXCEPTION_STACKTRACE]
    )
    assert called["value"] is True


def test_asyncio_unhandled_exception_emits_log(log_exporter, instrumentor):
    instrumentor.instrument()

    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda _loop, _context: None)
    try:
        exc, _ = _raise_value_error()
        loop.call_exception_handler({"exception": exc, "message": "boom"})
    finally:
        loop.close()

    log_record = _get_single_log(log_exporter)
    assert log_record.severity_text == "ERROR"
    attrs = log_record.attributes
    assert attrs[exception_attributes.EXCEPTION_TYPE] == "ValueError"
    assert attrs[exception_attributes.EXCEPTION_MESSAGE] == "boom"
    assert (
        "ValueError: boom" in attrs[exception_attributes.EXCEPTION_STACKTRACE]
    )


def test_uninstrument_restores_hooks(monkeypatch, log_exporter):
    instrumentor = UnhandledExceptionInstrumentor()

    original_sys = object()
    original_threading = object()

    monkeypatch.setattr("sys.excepthook", original_sys)
    monkeypatch.setattr("threading.excepthook", original_threading)

    instrumentor.instrument()
    instrumentor.uninstrument()

    assert sys.excepthook is original_sys
    assert threading.excepthook is original_threading


def test_helper_functions_cover_branches(monkeypatch):
    exc, tb = _raise_value_error()

    # _format_stacktrace covers exc_type/tb inference and None return
    assert _format_stacktrace(None, exc, None) is not None
    assert _format_stacktrace(None, None, None) is None

    # _exception_attributes covers exc_type inference
    attrs = _exception_attributes(None, exc, tb)
    assert attrs[exception_attributes.EXCEPTION_TYPE] == "ValueError"

    # _severity_number covers non-standard severity and None SeverityNumber
    assert _severity_number("INFO") is None
    monkeypatch.setattr(
        "opentelemetry.instrumentation.exceptions.SeverityNumber",
        None,
    )
    assert _severity_number("ERROR") is None


def test_internal_hooks_short_circuit(monkeypatch, log_exporter):
    instrumentor = UnhandledExceptionInstrumentor()
    instrumentor.instrument()

    # Already installed paths
    instrumentor._install_sys_hook()
    instrumentor._install_threading_hook()
    instrumentor._install_asyncio_hook()

    instrumentor.uninstrument()

    # Missing threading.excepthook path
    monkeypatch.delattr(threading, "excepthook", raising=False)
    instrumentor._install_threading_hook()
    instrumentor._restore_threading_hook()

    # Missing asyncio.BaseEventLoop path
    monkeypatch.setattr(asyncio, "BaseEventLoop", None)
    instrumentor._install_asyncio_hook()
    instrumentor._restore_asyncio_hook()
