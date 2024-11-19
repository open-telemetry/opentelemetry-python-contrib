OpenTelemetry logging integration
=================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-logging.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-logging/

Installation
------------

::

    pip install opentelemetry-instrumentation-logging

Log record enrichment behavior of logging instrumentation

"""
The OpenTelemetry ``logging`` integration automatically injects tracing context into log statements.
It's structured within an `if` statement that checks  [`set_logging_format`] is `True`, indicating that logging configuration should be applied.

The integration registers a custom log record factory with the the standard library logging module that automatically inject
tracing context into log record objects. Optionally, the integration can also call ``logging.basicConfig()`` to set a logging
format with placeholders for span ID, trace ID and service name.

1. **Determining the Log Format**: The code first attempts to determine the logging format by looking for a `logging_format` key in the [`kwargs`]( dictionary. If it's not found, it tries to fetch the value from an environment variable named [`OTEL_PYTHON_LOG_FORMAT`]. If neither is available, it defaults to a predefined constant [`DEFAULT_LOGGING_FORMAT`]. This approach provides flexibility, allowing the log format to be specified through function arguments, environment variables, or falling back to a default if neither is provided.

2. **Determining the Log Level**: Similarly, the log level is determined by looking for a [`log_level`] key in [`kwargs`](. If not found, it attempts to fetch a value from an environment variable [`OTEL_PYTHON_LOG_LEVEL`] and maps this value through a [`LEVELS`] dictionary to get the corresponding log level. If this process doesn't yield a result, it defaults to [`logging.INFO`]. This mechanism allows for dynamic adjustment of the log level based on runtime configurations or environment settings.

3. **Applying the Configuration**: Finally, with the determined [`log_format`] and [`log_level`](c, the code calls [`logging.basicConfig(format=log_format, level=log_level)`]. This function is a part of Python's standard logging library and is used to configure the basic settings of the logging system. It sets up the default format for log messages and the log level, which controls the severity of the messages that are processed.

The following keys are injected into log record objects by the factory:

- ``otelSpanID``
- ``otelTraceID``
- ``otelServiceName``
- ``otelTraceSampled``

The integration uses the following logging format by default:

.. code-block::

    {default_logging_format}
	
DEFAULT_LOGGING_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s resource.service.name=%(otelServiceName)s trace_sampled=%(otelTraceSampled)s] - %(message)s"

Enable trace context injection
------------------------------

The integration is opt-in and must be enabled explicitly by setting the environment variable ``OTEL_PYTHON_LOG_CORRELATION`` to ``true``.

``OTEL_PYTHON_LOG_CORRELATION`` to ``true`` calls ``logging.basicConfig()`` to set a logging format that actually makes
use of the injected variables.


Environment variables
---------------------

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

    LoggingInstrumentor().instrument(set_logging_format=True)


Note
-----

If you do not set ``OTEL_PYTHON_LOG_CORRELATION`` to ``true`` but instead set the logging format manually or through your framework, you must ensure that this
integration is enabled before you set the logging format. This is important because unless the integration is enabled, the tracing context variables
are not injected into the log record objects. This means any attempted log statements made after setting the logging format and before enabling this integration
will result in KeyError exceptions. Such exceptions are automatically swallowed by the logging module and do not result in crashes but you may still lose out
on important log messages.
"""


References
----------

* `OpenTelemetry logging integration <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/logging/logging.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
