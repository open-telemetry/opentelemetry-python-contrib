OpenTelemetry Baggage Span Processor
====================================

The BaggageSpanProcessor reads entries stored in Baggage
from the parent context and adds the baggage entries' keys and
values to the span as attributes on span start.

Add this span processor to a tracer provider.

Keys and values added to Baggage will appear on subsequent child
spans for a trace within this service *and* be propagated to external
services in accordance with any configured propagation formats
configured. If the external services also have a Baggage span
processor, the keys and values will appear in those child spans as
well.

⚠ Warning ⚠️

Do not put sensitive information in Baggage.

To repeat: a consequence of adding data to Baggage is that the keys and
values will appear in all outgoing HTTP headers from the application.

## Usage

Add the span processor when configuring the tracer provider.

To configure the span processor to copy all baggage entries during configuration:

```python
from opentelemetry.processor.baggage import BaggageSpanProcessor, ALLOW_ALL_BAGGAGE_KEYS

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(BaggageSpanProcessor(ALLOW_ALL_BAGGAGE_KEYS))
```

Alternatively, you can provide a custom baggage key predicate to select which baggage keys you want to copy.

For example, to only copy baggage entries that start with `my-key`:

```python
starts_with_predicate = lambda baggage_key: baggage_key.startswith("my-key")
tracer_provider.add_span_processor(BaggageSpanProcessor(starts_with_predicate))
```

For example, to only copy baggage entries that match the regex `^key.+`:

```python
regex_predicate = lambda baggage_key: baggage_key.startswith("^key.+")
tracer_provider.add_span_processor(BaggageSpanProcessor(regex_predicate))
```