OpenTelemetry Resource detectors for containers
==========================================================

|pypi|

.. |pypi| image:: TODO
   :target: TODO


This library provides custom resource detector for container platforms

Installation
------------

::

    pip install opentelemetry-resource-detector-container

---------------------------

Below is the give example for `opentelemetry-resource-detector-kubernetes`

.. code-block:: python

    import opentelemetry.trace as trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.resource.detector.container import (
        ContainerResourceDetector,
    )
    from opentelemetry.sdk.resources import get_aggregated_resources


    trace.set_tracer_provider(
        TracerProvider(
            resource=get_aggregated_resources(
                [
                    ContainerResourceDetector(),
                ]
            ),
        )
    )

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
