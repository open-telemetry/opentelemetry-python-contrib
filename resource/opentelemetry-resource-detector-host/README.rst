OpenTelemetry Resource detectors for containers
==========================================================

|pypi|

.. |pypi| image:: TODO
   :target: TODO


This library provides custom resource detector for container platforms

Installation
------------

::

    pip install opentelemetry-resource-detector-host

---------------------------

Usage example for `opentelemetry-resource-detector-host`

.. code-block:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.resource.detector.container import (
        HostResourceDetector,
    )
    from opentelemetry.sdk.resources import get_aggregated_resources


    trace.set_tracer_provider(
        TracerProvider(
            resource=get_aggregated_resources(
                [
                    HostResourceDetector(),
                ]
            ),
        )
    )

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
