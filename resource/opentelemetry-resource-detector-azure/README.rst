OpenTelemetry Resource detectors for Azure
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resource-detector-azure.svg
   :target: https://pypi.org/project/opentelemetry-resource-detector-azure/

This library contains OpenTelemetry `Resource Detectors <https://opentelemetry.io/docs/specs/otel/resource/sdk/#detecting-resource-information-from-the-environment>`_ for the following Azure resources:
 * `Azure App Service <https://azure.microsoft.com/en-us/products/app-service>`_
 * `Azure Virtual Machines <https://azure.microsoft.com/en-us/products/virtual-machines>`_
 * `Azure Functions (Experimental) <https://azure.microsoft.com/en-us/products/functions>`_

Installation
------------

::

    pip install opentelemetry-resource-detector-azure

---------------------------

Usage example for ``opentelemetry-resource-detector-azure``

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

Mappings
--------

The Azure App Service Resource Detector sets the following Resource Attributes:
 * ``service.name`` set to the value of the ``WEBSITE_SITE_NAME`` environment variable.
 * ``cloud.platform`` set to ``azure_app_service``.
 * ``cloud.provider`` set to ``azure``.
 * ``cloud.resource_id`` set using the ``WEBSITE_RESOURCE_GROUP``, ``WEBSITE_OWNER_NAME``, and ``WEBSITE_SITE_NAME`` environment variables.
 * ``cloud.region`` set to the value of the ``REGION_NAME`` environment variable.
 * ``deployment.environment`` set to the value of the ``WEBSITE_SLOT_NAME`` environment variable.
 * ``host.id`` set to the value of the ``WEBSITE_HOSTNAME`` environment variable.
 * ``service.instance.id`` set to the value of the ``WEBSITE_INSTANCE_ID`` environment variable.
 * ``azure.app.service.stamp`` set to the value of the ``WEBSITE_HOME_STAMPNAME`` environment variable.

The Azure VM Resource Detector sets the following Resource Attributes according to the response from the `Azure Metadata Service <https://learn.microsoft.com/azure/virtual-machines/instance-metadata-service?tabs=windows>`_:
 * ``azure.vm.scaleset.name`` set to the value of the ``vmScaleSetName`` field.
 * ``azure.vm.sku`` set to the value of the ``sku`` field.
 * ``cloud.platform`` set to the value of the ``azure_vm``.
 * ``cloud.provider`` set to the value of the ``azure``.
 * ``cloud.region`` set to the value of the ``location`` field.
 * ``cloud.resource_id`` set to the value of the ``resourceId`` field.
 * ``host.id`` set to the value of the ``vmId`` field.
 * ``host.name`` set to the value of the ``name`` field.
 * ``host.type`` set to the value of the ``vmSize`` field.
 * ``os.type`` set to the value of the ``osType`` field.
 * ``os.version`` set to the value of the ``version`` field.
 * ``service.instance.id`` set to the value of the ``vmId`` field.

The Azure Functions Resource Detector is currently experimental. It sets the following Resource Attributes:
 * ``service.name`` set to the value of the ``WEBSITE_SITE_NAME`` environment variable.
 * ``process.id`` set to the process ID collected from the running process.
 * ``cloud.platform`` set to ``azure_functions``.
 * ``cloud.provider`` set to ``azure``.
 * ``cloud.resource_id`` set using the ``WEBSITE_RESOURCE_GROUP``, ``WEBSITE_OWNER_NAME``, and ``WEBSITE_SITE_NAME`` environment variables.
 * ``cloud.region`` set to the value of the ``REGION_NAME`` environment variable.
 * ``faas.instance`` set to the value of the ``WEBSITE_INSTANCE_ID`` environment variable.
 * ``faas.max_memory`` set to the value of the ``WEBSITE_MEMORY_LIMIT_MB`` environment variable.

For more information, see the `Semantic Conventions for Cloud Resource Attributes <https://opentelemetry.io/docs/specs/otel/resource/semantic_conventions/cloud/>`_.

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_