OpenTelemetry Python Agent
==========================

A self-contained OpenTelemetry distribution: the API, SDK, exporters, the auto-instrumentation framework
and instrumentations, with all their dependencies vendored under ``opentelemetry.agent._vendor``. It can be
installed into any Python 3.10+ environment without affecting (or being affected by) the application's own
packages.

Usage
-----

::

    pip install opentelemetry-agent
    opentelemetry-instrument python app.py

``opentelemetry-instrument`` takes the same options and ``OTEL_*`` environment variables as the one from
``opentelemetry-instrumentation``. The ``otlp`` exporter uses ``http/protobuf``: the gRPC exporters aren't
included.

Isolation
---------

* Only the vendored plugins (exporters, propagators, samplers, resource detectors) and instrumentations are
  discovered; OpenTelemetry packages installed in the application's environment aren't used.
* The application's own ``opentelemetry-api`` (if any) is a separate copy, bridged to the agent: spans it
  records are exported by the agent's SDK, and they parent (and are parented by) the agent's
  instrumentation spans. ``opentelemetry-instrument`` selects the bridge by setting ``OTEL_PYTHON_CONTEXT``
  and ``OTEL_PYTHON_TRACER_PROVIDER`` to ``opentelemetry_agent``, unless they're already set; a tracer
  provider set by the application before its first ``get_tracer_provider()`` call is kept. Metrics and
  logs recorded with the application's API don't reach the agent's providers yet. Tested with
  ``opentelemetry-api`` 1.16 and later.
* ``opentelemetry-instrumentation`` installs an ``opentelemetry-instrument`` script as well; when both are
  installed, the package installed last owns it.
