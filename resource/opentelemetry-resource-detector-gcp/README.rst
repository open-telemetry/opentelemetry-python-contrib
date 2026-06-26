OpenTelemetry Google Cloud Resource Detector
============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resource-detector-gcp.svg
   :target: https://pypi.org/project/opentelemetry-resource-detector-gcp/

This library provides support for detecting GCP resources like GCE, GKE, etc.

Installation
------------

::

    pip install opentelemetry-resource-detector-gcp

Usage
-----

.. code-block:: python

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_INSTANCE_ID, Resource

    # This will use the GoogleCloudResourceDetector under the covers.
    resource = Resource.create(
        attributes={
            # Use the PID as the service.instance.id to avoid duplicate timeseries
            # from different Gunicorn worker processes.
            SERVICE_INSTANCE_ID: f"worker-{os.getpid()}",
        }
    )
    traceProvider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter())
    traceProvider.add_span_processor(processor)
    trace.set_tracer_provider(traceProvider)

References
----------

* `Cloud Monitoring <https://cloud.google.com/monitoring>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
