OpenTelemetry Resources for container-detectors-kubernetes
==========================================================

|pypi|

.. |pypi| image:: TODO
   :target: TODO


This library provides container property detection features which can help
correlate different spans and traces across different systems.

Installation
------------

::

    pip install opentelemetry-resource-detector-kubernetes

----------------------------

Below is the give example for `opentelemetry-resource-detector-kubernetes`

.. code-block:: python

    import opentelemetry.trace as trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.resource.detector.kubernetes import (
        KubernetesResourceDetector,
    )
    from opentelemetry.sdk.resources import get_aggregated_resources

    trace.set_tracer_provider(
        TracerProvider(
            resource=get_aggregated_resources(
                [
                    KubernetesResourceDetector(),
                ]
            ),
        )
    )


References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
