OpenTelemetry logging integration
=================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-logging.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-logging/

Installation
------------

::

    pip install opentelemetry-instrumentation-logging

What it does
------------

This instrumentation adds an OpenTelemetry ``LoggingHandler`` to the Python
root logger. Each standard-library ``logging`` record is converted to an
OpenTelemetry log and sent through the configured logger provider/exporter;
installing this package is therefore different from merely configuring a
Python logging format. The handler can be disabled during auto-instrumentation
with ``OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION=false``.

The handler preserves the record's message, severity, logger name, and custom
attributes. When ``OTEL_PYTHON_LOG_CODE_ATTRIBUTES=true`` it also adds
``code.file.path``, ``code.function.name``, and ``code.line.number``. Exception
records include the standard exception type, message, and stack trace fields.

Trace-context enrichment is a separate opt-in feature. It adds these fields to
each ``LogRecord`` without changing the logging output unless a format is
configured:

* ``otelSpanID``
* ``otelTraceID``
* ``otelTraceSampled``
* ``otelServiceName``

Enable it with ``OTEL_PYTHON_LOG_CORRELATION=true`` or
``LoggingInstrumentor().instrument(set_logging_format=True)``. If the
application owns its format, use
``LoggingInstrumentor().instrument(inject_trace_context=True)`` instead.

Configuration
-------------

The following environment variables configure the instrumentation:

* ``OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION``: set to ``false`` to skip handler
  installation (default ``true``).
* ``OTEL_PYTHON_LOG_CORRELATION``: enable trace-context injection and the
  default correlated format (default ``false``).
* ``OTEL_PYTHON_LOG_FORMAT``: replace the default format when correlation is
  enabled; ``logging_format=`` is the programmatic equivalent.
* ``OTEL_PYTHON_LOG_HANDLER_LEVEL``: export only records at or above a named
  level such as ``debug``, ``info``, ``warning``, or ``error``.
* ``OTEL_PYTHON_LOG_CODE_ATTRIBUTES``: add source-location attributes
  (default ``false``).

The programmatic API also accepts ``log_level=`` for the configured logging
level and ``log_hook=`` for application-specific record enrichment. Configure
a logger provider/exporter separately; this package supplies the bridge from
stdlib logging to OpenTelemetry logs.


References
----------

* `OpenTelemetry logging integration <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/logging/logging.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
