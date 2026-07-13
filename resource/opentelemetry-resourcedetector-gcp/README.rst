OpenTelemetry Google Cloud Resource Detector
============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resourcedetector-gcp.svg
   :target: https://pypi.org/project/opentelemetry-resourcedetector-gcp/

This library provides support for detecting GCP resources like GCE, GKE, etc.

Installation
------------

::

    pip install opentelemetry-resourcedetector-gcp

Usage
-----

The `GoogleCloudResourceDetector` is automatically used by the OpenTelemetry SDK 
when it is installed in the python environment.

.. code-block:: python

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry import trace

    # GoogleCloudResourceDetector will automatically get used here if it's installed in the environment.
    traceProvider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter())
    traceProvider.add_span_processor(processor)
    trace.set_tracer_provider(traceProvider)

References
----------

* `GCP Open Telemetry Docs <https://cloud.google.com/learn/what-is-opentelemetry>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
