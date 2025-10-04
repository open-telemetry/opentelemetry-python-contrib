OpenTelemetry GenAI Traceloop Emitters
======================================

This package provides the legacy Traceloop-compatible span emitter that was
previously bundled with ``opentelemetry-util-genai``. It exposes an entry point
named ``traceloop`` under ``opentelemetry_util_genai_emitters`` so that the
refactored composite emitter can discover and append the Traceloop span logic
at runtime.

Installation
------------

.. code-block:: bash

   pip install opentelemetry-util-genai-emitters-traceloop

When working from the refactor branch you can use the editable install:

.. code-block:: bash

   pip install -e util/opentelemetry-util-genai-emitters-traceloop

Usage
-----

Add ``traceloop_compat`` to ``OTEL_INSTRUMENTATION_GENAI_EMITTERS`` (or the
category-specific environment variables) once the package is installed:

.. code-block:: bash

   export OTEL_INSTRUMENTATION_GENAI_EMITTERS="span_metric_event,traceloop_compat"

The emitter will append a span that mirrors the original Traceloop LangChain
telemetry, including optional message content capture when span or event
content capture is enabled in ``opentelemetry-util-genai``.

Tests
-----
Run the package's unit tests with:

.. code-block:: bash

   pytest util/opentelemetry-util-genai-emitters-traceloop/tests

