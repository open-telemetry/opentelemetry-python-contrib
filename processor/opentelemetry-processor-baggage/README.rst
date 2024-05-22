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
