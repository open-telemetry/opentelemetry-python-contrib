OpenTelemetry GCP Credential Provider for OTLP Exporters
========================================================

.. image:: https://badge.fury.io/py/opentelemetry-exporter-credential-provider-gcp.svg
    :target: https://badge.fury.io/py/opentelemetry-exporter-credential-provider-gcp

.. image:: https://readthedocs.org/projects/google-cloud-opentelemetry/badge/?version=latest
    :target: https://google-cloud-opentelemetry.readthedocs.io/en/latest/?badge=latest
    :alt: Documentation Status

This library provides support for supplying your machine's Application Default Credentials (https://cloud.google.com/docs/authentication/application-default-credentials)
to the OTLP Exporters created automatically by OpenTelemetry Python's auto instrumentation.
These credentials authorize OTLP traces to be sent to `telemetry.googleapis.com`.

Currently `telemetry.googleapis.com` only supports OTLP traces, but eventually the endpoint will
support OTLP logs and metrics too.

To learn more about instrumentation and observability, including opinionated recommendations
for Google Cloud Observability, visit `Instrumentation and observability
<https://cloud.google.com/stackdriver/docs/instrumentation/overview>`_.

For how to export trace data when you use manual instrumentation visit `Migrate from the Trace exporter to the OTLP endpoint
<https://cloud.google.com/trace/docs/migrate-to-otlp-endpoints>`_.

Installation
------------

.. code:: bash

    pip install opentelemetry-exporter-credential-provider-gcp

Usage
-----

Your installed HTTP/GRPC OTLP Exporter must be at release `>=1.37` for this feature.

Set the following environment variables:
`export OTEL_RESOURCE_ATTRIBUTES="gcp.project_id=<project-id>"`
`export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="https://telemetry.googleapis.com:443/v1/traces"`

If you plan to have python auto instrumentation use the GRPC OTLP Exporter to send traces to Cloud Trace:
`export OTEL_PYTHON_EXPORTER_OTLP_GRPC_TRACES_CREDENTIAL_PROVIDER=gcp_grpc_credentials`

If you plan to have python auto instrumentation use the HTTP OTLP Exporter to send traces to Cloud Trace:
`export OTEL_PYTHON_EXPORTER_OTLP_HTTP_TRACES_CREDENTIAL_PROVIDER=gcp_http_credentials`


References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
