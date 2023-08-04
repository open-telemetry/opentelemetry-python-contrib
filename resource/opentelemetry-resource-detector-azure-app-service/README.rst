OpenTelemetry Resource detectors for Azure App Services
==========================================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resource-detector-azure-app-service.svg
   :target: https://pypi.org/project/opentelemetry-resource-detector-azure-app-service/


This library provides custom resource detector for Azure App Services

Installation
------------

::

    pip install opentelemetry-resource-detector-azure-app-service

---------------------------

Usage example for `opentelemetry-resource-detector-azure-app-service`

.. code-block:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.resource.detector.azure.app_service import (
        AzureAppServiceResourceDetector,
    )
    from opentelemetry.sdk.resources import get_aggregated_resources


    trace.set_tracer_provider(
        TracerProvider(
            resource=get_aggregated_resources(
                [
                    AzureAppServiceResourceDetector(),
                ]
            ),
        )
    )

You can also enable the App Service Resource Detector by adding `azure_app_service` to the `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` environment variable:

`export OTEL_EXPERIMENTAL_RESOURCE_DETECTORS=azure_app_service`

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
