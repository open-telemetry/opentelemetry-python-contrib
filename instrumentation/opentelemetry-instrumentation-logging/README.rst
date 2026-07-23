OpenTelemetry logging integration
=================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-logging.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-logging/

This instrumentation enriches Python log records with OpenTelemetry trace context
and optionally forwards log messages to the OpenTelemetry Logs SDK. It does **not**
replace the standard ``logging`` module — it enhances it.

Installation
------------

::

    pip install opentelemetry-instrumentation-logging

Usage
-----

Trace context injection
***********************

The primary feature of this instrumentation is injecting trace context attributes
into every log record. This enables log correlation — connecting logs to the traces
that produced them.

Pass ``inject_trace_context=True`` to add the following attributes to every log record
without changing the logging format:

.. code-block:: python

    import logging

    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    LoggingInstrumentor().instrument(inject_trace_context=True)

    logging.warning("This log record now has otelTraceID and otelSpanID")

The injected attributes are:

- ``otelTraceID`` — The current trace ID (hex, or ``"0"`` if no active span)
- ``otelSpanID`` — The current span ID (hex, or ``"0"`` if no active span)
- ``otelTraceSampled`` — Whether the current span is sampled (``True``/``False``)
- ``otelServiceName`` — The service name from the tracer provider's resource

Auto-formatting with trace context
***********************************

To both inject trace context and update the logging format to display it, use
``set_logging_format=True``:

.. code-block:: python

    import logging

    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    LoggingInstrumentor().instrument(set_logging_format=True)

    logging.warning("OTel test")

Output::

    2025-03-05 09:40:04,398 WARNING [root] [example.py:7] [trace_id=0 span_id=0 resource.service.name= trace_sampled=False] - OTel test

Configuration
-------------

Environment variables
*********************

The following environment variables configure the instrumentation:

- ``OTEL_PYTHON_LOG_CORRELATION`` — Set to ``true`` to enable trace context injection and format modification (equivalent to ``set_logging_format=True``). Default: ``false``.
- ``OTEL_PYTHON_LOG_FORMAT`` — Custom logging format string. Used when correlation is enabled. Falls back to a built-in default that includes trace context fields.
- ``OTEL_PYTHON_LOG_LEVEL`` — Log level for ``logging.basicConfig()`` when format modification is active. Accepts ``debug``, ``info``, ``warning``, ``error``. Default: ``info``.
- ``OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION`` — Set to ``false`` to disable the automatic log-to-OTel handler. Default: ``true``.
- ``OTEL_PYTHON_LOG_HANDLER_LEVEL`` — Minimum level for the OpenTelemetry log handler. Logs below this level are not forwarded to the OTel SDK.
- ``OTEL_PYTHON_LOG_CODE_ATTRIBUTES`` — Set to ``true`` to add code attributes (file, line number, function) to emitted OTel log records.

Log hook
********

A ``log_hook`` callback can execute custom logic on each log record:

.. code-block:: python

    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.trace import Span
    from logging import LogRecord

    def log_hook(span: Span, record: LogRecord):
        if span and span.is_recording():
            record.custom_attribute = "some-value"

    LoggingInstrumentor().instrument(
        inject_trace_context=True,
        log_hook=log_hook,
    )

References
----------

* `OpenTelemetry logging integration <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/logging/logging.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
