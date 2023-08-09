OpenTelemetry Resource detectors for Azure
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resource-detector-azure.svg
   :target: https://pypi.org/project/opentelemetry-resource-detector-azure/


The Azure App Service Resource Detector sets the following Resource Attributes:
 * `service.name` set to the value of the WEBSITE_SITE_NAME environment variable.
 * `cloud.provider` set to the value of the "azure".
 * `cloud.platform` set to the value of the "azure_app_service".
 * `cloud.resource_id` set using the WEBSITE_RESOURCE_GROUP WEBSITE_OWNER_NAME and WEBSITE_SITE_NAME environment variables.
 * `cloud.region` set to the value of the REGION_NAME environment variable.
 * `deployment.environment` set to the value of the WEBSITE_SLOT_NAME environment variable.
 * `host.id` set to the value of the WEBSITE_HOSTNAME environment variable.
 * `service.instance.id` set to the value of the WEBSITE_INSTANCE_ID environment variable.
 * `azure.app.service.stamp` set to the value of the WEBSITE_HOME_STAMPNAME environment variable.

The Azure VM Resource Detector sets the following Resource Attributes:
 * `azure.vm.scaleset.name`
 * `azure.vm.sku`
 * `cloud.platform`
 * `cloud.provider`
 * `cloud.region`
 * `cloud.resource_id`
 * `host.id`
 * `host.name`
 * `host.type`
 * `os.type`
 * `os.version`
 * `service.instance.id`

 For more information, see the Semantic Conventions for Cloud Resource Attributes.

Installation
------------

::

    pip install opentelemetry-resource-detector-azure

---------------------------

Usage example for `opentelemetry-resource-detector-azure`

.. code-block:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.resource.detector.azure.app_service import (
        AzureAppServiceResourceDetector,
        AzureVMResourceDetector,
    )
    from opentelemetry.resource.detector.azure.vm import (
        AzureVMResourceDetector,
    )
    from opentelemetry.sdk.resources import get_aggregated_resources


    trace.set_tracer_provider(
        TracerProvider(
            resource=get_aggregated_resources(
                [
                    AzureAppServiceResourceDetector(),
                    AzureVMResourceDetector(),
                ]
            ),
        )
    )

You can also enable the Resource Detectors by adding `azure_app_service` and/or `azure_vm` to the `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` environment variable:

`export OTEL_EXPERIMENTAL_RESOURCE_DETECTORS=azure_app_service,azure_vm`

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Resource Detector Docs <https://opentelemetry.io/docs/specs/otel/resource/sdk/#detecting-resource-information-from-the-environment>`
* `Cloud Semantic Conventions <https://opentelemetry.io/docs/specs/otel/resource/semantic_conventions/cloud/>`_
