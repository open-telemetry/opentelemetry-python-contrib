Stable Semantic Conventions
***************************

This instrumentation supports the semantic convention migration plan. You can control
which semantic conventions are emitted by setting the
``OTEL_SEMCONV_STABILITY_OPT_IN`` environment variable.

This instrumentation supports both database and HTTP semantic conventions. Set ``OTEL_SEMCONV_STABILITY_OPT_IN`` to:

- ``database`` - emit the stable database and networking conventions, and stop emitting
  the old experimental database conventions.
- ``database/dup`` - emit both the old experimental and stable database
  conventions during a transition period.
- ``http`` - emit the stable HTTP and networking conventions, and stop emitting
  the old experimental HTTP and networking conventions.
- ``http/dup`` - emit both the old experimental and stable HTTP and networking
  conventions during a transition period.

The environment variable accepts a comma-separated list of opt-in values. For
example, ``database,http`` enables both stable database and HTTP semantic conventions.

By default, when the environment variable is not set, the old experimental conventions
are emitted.
