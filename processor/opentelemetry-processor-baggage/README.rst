OpenTelemetry Baggage Span Processor
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-processor-baggage.svg
   :target: https://pypi.org/project/opentelemetry-processor-baggage/

The BaggageSpanProcessor reads entries stored in Baggage
from the parent context and adds the baggage entries' keys and
values to the span as attributes on span start.

Installation
------------

::

    pip install opentelemetry-processor-baggage

Add this span processor to a tracer provider.

Keys and values added to Baggage will appear on subsequent child
spans for a trace within this service *and* be propagated to external
services in accordance with any configured propagation formats
configured. If the external services also have a Baggage span
processor, the keys and values will appear in those child spans as
well.

[!WARNING]

Do not put sensitive information in Baggage.

To repeat: a consequence of adding data to Baggage is that the keys and
values will appear in all outgoing HTTP headers from the application.

## Usage

Add the span processor when configuring the tracer provider.

To configure the span processor to copy all baggage entries during configuration:

::

    from opentelemetry.processor.baggage import BaggageSpanProcessor, ALLOW_ALL_BAGGAGE_KEYS

    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(BaggageSpanProcessor(ALLOW_ALL_BAGGAGE_KEYS))


Alternatively, you can provide a custom baggage key predicate to select which baggage keys you want to copy.

For example, to only copy baggage entries that start with `my-key`:

::

    starts_with_predicate = lambda baggage_key: baggage_key.startswith("my-key")
    tracer_provider.add_span_processor(BaggageSpanProcessor(starts_with_predicate))


For example, to only copy baggage entries that match the regex `^key.+`:

::

    regex_predicate = lambda baggage_key: baggage_key.startswith("^key.+")
    tracer_provider.add_span_processor(BaggageSpanProcessor(regex_predicate))


References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
