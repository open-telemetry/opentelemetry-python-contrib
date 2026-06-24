# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

DEFAULT_LOGGING_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s resource.service.name=%(otelServiceName)s trace_sampled=%(otelTraceSampled)s] - %(message)s"


_MODULE_DOC = """
The OpenTelemetry ``logging`` instrumentation automatically instruments Python logging
with a handler to convert Python log messages into OpenTelemetry logs and export them.
You can disable this by setting ``OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION`` to ``false``.

.. warning::

    This package provides a logging handler to replace the deprecated one in ``opentelemetry-sdk``.
    Therefore if you have ``opentelemetry-instrumentation-logging`` installed, you don't need to set the
    ``OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED`` environment variable to ``true``.
    By default, this instrumentation does not add ``code`` namespace attributes as the SDK's logger does, but adding them can be enabled by using the
    ``OTEL_PYTHON_LOG_CODE_ATTRIBUTES`` environment variable.

Enable trace context injection
------------------------------

The OpenTelemetry ``logging`` integration can also be configured to inject tracing context into log statements.

The integration registers a custom log record factory with the the standard library logging module that automatically inject
tracing context into log record objects. Optionally, the integration can also call ``logging.basicConfig()`` to set a logging
format with placeholders for span ID, trace ID and service name.

The following keys are injected into log record objects by the factory:

- ``otelSpanID``
- ``otelTraceID``
- ``otelServiceName``
- ``otelTraceSampled``

The integration uses the following logging format by default:

.. code-block::

    {default_logging_format}

Trace context injection is opt-in and can be enabled in two ways:

- Pass ``inject_trace_context=True`` to inject trace context attributes into every log record without modifying
  the logging format. Use this when you manage the logging format yourself but still want
  ``otelSpanID``, ``otelTraceID``, ``otelTraceSampled``, and ``otelServiceName`` available on each record.
- Set ``OTEL_PYTHON_LOG_CORRELATION`` to ``true`` (or pass ``set_logging_format=True``) to inject the same
  trace context attributes and call ``logging.basicConfig()`` with a format string that includes them.

Environment variables
---------------------

.. envvar:: OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION

Set this env var to ``false`` to skip installing the logging handler provided by this package.

The default value is ``true``.

.. envvar:: OTEL_PYTHON_CODE_ATTRIBUTES

Set this env var to ``true`` to add ``code`` attributes (``code.file.path``, ``code.function.name``, ``code.line.number``) to OpenTelemetry logs, referencing the Python source location that emitted each log message.

The default value is ``false``.

.. envvar:: OTEL_PYTHON_LOG_CORRELATION

This env var must be set to ``true`` in order to enable trace context injection into logs by calling ``logging.basicConfig()`` and
setting a logging format that makes use of the injected tracing variables.

Alternatively, ``set_logging_format`` argument can be set to ``True`` when initializing the ``LoggingInstrumentor`` class to achieve the
same effect.

.. code-block::

    LoggingInstrumentor(set_logging_format=True)

The default value is ``false``.

.. envvar:: OTEL_PYTHON_LOG_FORMAT

This env var can be used to instruct the instrumentation to use a custom logging format.

Alternatively, a custom logging format can be passed to the ``LoggingInstrumentor`` as the ``logging_format`` argument. For example:

.. code-block::

    LoggingInstrumentor(logging_format='%(msg)s [span_id=%(span_id)s]')


The default value is:

.. code-block::

    {default_logging_format}

.. envvar:: OTEL_PYTHON_LOG_HANDLER_LEVEL

Set this env var to filter which log records are exported by OpenTelemetry``LoggingHandler`` instrumentation.
Accepts case-insensitive level names: ``notset``, ``debug``, ``info``, ``warning``, ``error``.
Only records at or above this level will be exported.
For example, setting this to warning means DEBUG and INFO logs are still handled by your normal logging setup,
but they are not exported as OTel logs. Unrecognized values fall back to ``notset``.

Alternatively, the level can be set via the ``log_handler_level`` argument:

.. code-block::

    LoggingInstrumentor(log_handler_level=logging.WARNING)

The default value is ``notset``.

.. envvar:: OTEL_PYTHON_LOG_LEVEL

This env var can be used to set a custom logging level.

Alternatively, log level can be passed to the ``LoggingInstrumentor`` during initialization. For example:

.. code-block::

    LoggingInstrumentor(log_level=logging.DEBUG)


The default value is ``info``.

Options are:

- ``info``
- ``error``
- ``debug``
- ``warning``

Manually calling logging.basicConfig
------------------------------------

``logging.basicConfig()`` can be called to set a global logging level and format. Only the first ever call has any effect on the global logger.
Any subsequent calls have no effect and do not override a previously configured global logger. This integration calls ``logging.basicConfig()`` for you
when ``OTEL_PYTHON_LOG_CORRELATION`` is set to ``true``. It uses the format and level specified by ``OTEL_PYTHON_LOG_FORMAT`` and ``OTEL_PYTHON_LOG_LEVEL``
environment variables respectively.

If you code or some other library/framework you are using calls logging.basicConfig before this integration is enabled, then this integration's logging
format will not be used and log statements will not contain tracing context. For this reason, you'll need to make sure this integration is enabled as early
as possible in the service lifecycle or your framework is configured to use a logging format with placeholders for tracing context. This can be achieved by
adding the following placeholders to your logging format:

.. code-block::

    %(otelSpanID)s %(otelTraceID)s %(otelServiceName)s %(otelTraceSampled)s



API
-----

.. code-block:: python

    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    # inject trace context attributes only (manage your own format)
    LoggingInstrumentor().instrument(inject_trace_context=True)

.. code-block:: python

    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    # inject trace context attributes and set the logging format
    LoggingInstrumentor().instrument(set_logging_format=True)


Note
-----

If you set a logging format with trace context placeholders (e.g. ``%(otelSpanID)s``) but do not enable
trace context injection via ``inject_trace_context=True`` or ``set_logging_format=True``, the placeholders
will not be populated. Any log statements emitted before injection is enabled will result in ``KeyError``
exceptions, which the logging module silently swallows. Enable this integration as early as possible to
avoid these issues.
""".format(default_logging_format=DEFAULT_LOGGING_FORMAT)
