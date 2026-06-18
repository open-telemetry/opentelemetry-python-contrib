OpenTelemetry logging integration
=================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-logging.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-logging/

Installation
------------

::

    pip install opentelemetry-instrumentation-logging

Usage
-----

The logging instrumentation installs a standard library ``logging`` handler that
exports Python log records as OpenTelemetry logs. It can also inject the active
trace context into every ``logging.LogRecord`` so that logs can be correlated
with traces.

.. code-block:: python

    import logging

    from opentelemetry.instrumentation.logging import LoggingInstrumentor

    LoggingInstrumentor().instrument()

    logging.warning("OpenTelemetry log export")

Trace context injection
-----------------------

Trace context injection is opt-in. Enable it with
``OTEL_PYTHON_LOG_CORRELATION=true`` or by passing
``set_logging_format=True`` when instrumenting:

.. code-block:: python

    LoggingInstrumentor().instrument(set_logging_format=True)

When enabled, the instrumentation registers a custom log record factory and
adds the following attributes to each log record:

* ``otelSpanID``
* ``otelTraceID``
* ``otelServiceName``
* ``otelTraceSampled``

The default logging format includes those attributes:

.. code-block:: text

    %(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s resource.service.name=%(otelServiceName)s trace_sampled=%(otelTraceSampled)s] - %(message)s

Custom attributes can also be added to records with the ``log_hook`` argument.

Configuration
-------------

The logging instrumentation supports the following environment variables and
matching ``LoggingInstrumentor().instrument(...)`` arguments:

* ``OTEL_PYTHON_LOG_AUTO_INSTRUMENTATION`` / ``enable_log_auto_instrumentation``
  controls whether the OpenTelemetry logging handler is installed. The default
  is ``true``.
* ``OTEL_PYTHON_LOG_CORRELATION`` / ``set_logging_format`` enables trace context
  injection and configures ``logging.basicConfig()`` with a format that uses the
  injected attributes. The default is ``false``.
* ``OTEL_PYTHON_LOG_FORMAT`` / ``logging_format`` sets the logging format used
  when log correlation is enabled.
* ``OTEL_PYTHON_LOG_LEVEL`` / ``log_level`` sets the level passed to
  ``logging.basicConfig()`` when log correlation is enabled.
* ``OTEL_PYTHON_LOG_HANDLER_LEVEL`` / ``log_handler_level`` filters which
  records are exported by the OpenTelemetry logging handler.
* ``OTEL_PYTHON_LOG_CODE_ATTRIBUTES`` / ``log_code_attributes`` adds
  ``code.file.path``, ``code.function.name``, and ``code.line.number`` to
  exported OpenTelemetry log attributes. The default is ``false``.


References
----------

* `Generated logging instrumentation documentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/logging/logging.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
