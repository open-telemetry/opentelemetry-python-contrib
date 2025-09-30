# ...existing code...
OTEL_INSTRUMENTATION_GENAI_GENERATOR = "OTEL_INSTRUMENTATION_GENAI_GENERATOR"
"""
.. envvar:: OTEL_INSTRUMENTATION_GENAI_GENERATOR

Select telemetry generator strategy. Accepted values (case-insensitive):

* ``span`` (default) - spans only (SpanGenerator emitter)
* ``span_metric`` - spans + metrics (composed Span + Metrics emitters)
* ``span_metric_event`` - spans + metrics + content events (composed Span + Metrics + ContentEvents emitters)

Invalid or unset values fallback to ``span``.
"""
# ...existing code...
