OpenTelemetry Resource detectors for Azure Virtual Machines
==========================================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resource-detector-azure-vm.svg
   :target: https://pypi.org/project/opentelemetry-resource-detector-azure-vm/


This library provides custom resource detector for Azure VMs. OpenTelemetry Python has an experimental feature whereby Resource Detectors can be injected to Resource Attributes. This package includes a resource detector for Azure VM. This detector fills out the following Resource Attributes:
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

    pip install opentelemetry-resource-detector-azure-vm

---------------------------

Usage example for `opentelemetry-resource-detector-azure-vm`

.. code-block:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.resource.detector.azure.vm import (
        AzureVMResourceDetector,
    )
    from opentelemetry.sdk.resources import get_aggregated_resources


    trace.set_tracer_provider(
        TracerProvider(
            resource=get_aggregated_resources(
                [
                    AzureVMResourceDetector(),
                ]
            ),
        )
    )

You can also enable the Azure VM Resource Detector by adding `azure_vm` to the `OTEL_EXPERIMENTAL_RESOURCE_DETECTORS` environment variable:

`export OTEL_EXPERIMENTAL_RESOURCE_DETECTORS=azure_vm`

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Resource Detector Docs <https://opentelemetry.io/docs/specs/otel/resource/sdk/#detecting-resource-information-from-the-environment>`
* `Cloud Semantic Conventions <https://opentelemetry.io/docs/specs/otel/resource/semantic_conventions/cloud/>`_
