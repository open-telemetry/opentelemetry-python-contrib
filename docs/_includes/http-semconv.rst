Stable Semantic Conventions
***************************

This instrumentation supports the semantic convention migration plan. You can control
which semantic conventions are emitted by setting the
``OTEL_SEMCONV_STABILITY_OPT_IN`` environment variable.

For HTTP instrumentations, set ``OTEL_SEMCONV_STABILITY_OPT_IN`` to:

- ``http`` - emit the stable HTTP and networking conventions, and stop emitting
  the old experimental HTTP and networking conventions.
- ``http/dup`` - emit both the old experimental and stable HTTP and networking
  conventions during a transition period.

The environment variable accepts a comma-separated list of opt-in values. For
example, ``http,database/dup`` enables stable HTTP semantic conventions and emits
both old and stable database semantic conventions.

By default, when the environment variable is not set, the old experimental HTTP
and networking conventions are emitted.
