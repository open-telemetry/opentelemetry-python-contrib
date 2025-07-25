OpenTelemetry Partial Span Processor
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-processor-partial-span.svg
   :target: https://pypi.org/project/opentelemetry-processor-partial-span/

The PartialSpanProcessor is an OpenTelemetry span processor that emits logs at regular intervals (referred to as "heartbeats") during the lifetime of a span and when the span ends.
This processor is useful for monitoring long-running spans by providing periodic updates.

Features
----
* Emits periodic heartbeat logs for active spans.
* Logs span data in JSON format.
* Configurable heartbeat interval, initial delay, and processing interval.
* Supports integration with any logging framework.


Installation
----

::

    pip install opentelemetry-processor-partial-span

Usage
----

To use the PartialSpanProcessor, add it to your tracer provider during setup:

::

    from opentelemetry.processor.partial_span import PartialSpanProcessor
    from opentelemetry.sdk.trace import TracerProvider
    import logging

    # Configure a logger
    logger = logging.getLogger("example")
    logger.setLevel(logging.INFO)

    # Create a tracer provider
    tracer_provider = TracerProvider()

    # Add the PartialSpanProcessor
    tracer_provider.add_span_processor(
        PartialSpanProcessor(
            logger=logger,
            heartbeat_interval_millis=5000,  # Heartbeat interval in milliseconds
            initial_heartbeat_delay_millis=1000,  # Initial delay in milliseconds
            process_interval_millis=5000  # Processing interval in milliseconds
        )
    )

For more info check `example.py`

Configuration Parameters
----

* `logger`: A `logging.Logger` instance used to emit logs.
* `heartbeat_interval_millis`: The interval (in milliseconds) between heartbeat logs. Must be greater than 0.
* `initial_heartbeat_delay_millis`: The delay (in milliseconds) before the first heartbeat log. Must be greater than or equal to 0.
* `process_interval_millis`: The interval (in milliseconds) at which the processor checks for spans to log. Must be greater than 0.


References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
