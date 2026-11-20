Stable Semantic Conventions
***************************

This instrumentation supports the semantic convention migration plan. You can control
which semantic conventions are emitted by setting the
``OTEL_SEMCONV_STABILITY_OPT_IN`` environment variable.

For database instrumentations, set ``OTEL_SEMCONV_STABILITY_OPT_IN`` to:

- ``database`` - emit the stable database and networking conventions, and stop emitting
  the old experimental database conventions.
- ``database/dup`` - emit both the old experimental and stable database
  conventions during a transition period.

The environment variable accepts a comma-separated list of opt-in values. For
example, ``database,http/dup`` enables stable database semantic conventions and emits
both old and stable HTTP semantic conventions.

By default, when the environment variable is not set, the old experimental database
conventions are emitted.
