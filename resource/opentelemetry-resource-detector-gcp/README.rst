OpenTelemetry Resource detectors for gcp
==========================================================

|pypi|

.. |pypi| image:: TODO
   :target: TODO


This library provides custom resource detector for gcp

Installation
------------

::

    pip install opentelemetry-resource-detector-gcp

---------------------------

Usage example for `opentelemetry-resource-detector-gcp`

.. code-block:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.resource.detector.gcp import (
        GoogleCloudResourceDetector,
    )
    from opentelemetry.sdk.resources import get_aggregated_resources


    trace.set_tracer_provider(
        TracerProvider(
            resource=get_aggregated_resources(
                [
                    GoogleCloudResourceDetector(),
                ]
            ),
        )
    )

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
