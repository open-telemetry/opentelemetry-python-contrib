OpenTelemetry Resource detectors for Azure App Services
==========================================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resource-detector-azure-app-service.svg
   :target: https://pypi.org/project/opentelemetry-resource-detector-azure-app-service/


This library provides custom resource detector for Azure App Services. OpenTelemetry Python has an experimental feature whereby Resource Detectors can be injected to Resource Attributes. This package includes a resource detector for Azure App Service. This detector fills out the following Resource Attributes:
 * `service.name` set to the value of the WEBSITE_SITE_NAME environment variable.
 * `cloud.provider` set to the value of the "azure".
 * `cloud.platform` set to the value of the "azure_app_service".
 * `cloud.resource_id` set using the WEBSITE_RESOURCE_GROUP WEBSITE_OWNER_NAME and WEBSITE_SITE_NAME environment variables.
 * `cloud.region` set to the value of the REGION_NAME environment variable.
 * `deployment.environment` set to the value of the WEBSITE_SLOT_NAME environment variable.
 * `host.id` set to the value of the WEBSITE_HOSTNAME environment variable.
 * `service.instance.id` set to the value of the WEBSITE_INSTANCE_ID environment variable.
 * `azure.app.service.stamp` set to the value of the WEBSITE_HOME_STAMPNAME environment variable.

 ResourceAttributes.CLOUD_REGION: _REGION_NAME,
    ResourceAttributes.DEPLOYMENT_ENVIRONMENT: _WEBSITE_SLOT_NAME,
    ResourceAttributes.HOST_ID: _WEBSITE_HOSTNAME,
    ResourceAttributes.SERVICE_INSTANCE_ID: _WEBSITE_INSTANCE_ID,
    _AZURE_APP_SERVICE_STAMP_RESOURCE_ATTRIBUTE: _WEBSITE_HOME_STAMPNAME,

 For more information, see the Semantic Conventions for Cloud Resource Attributes.

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
* `Resource Detector Docs <https://opentelemetry.io/docs/specs/otel/resource/sdk/#detecting-resource-information-from-the-environment>`
* `Cloud Semantic Conventions <https://opentelemetry.io/docs/specs/otel/resource/semantic_conventions/cloud/>`_
