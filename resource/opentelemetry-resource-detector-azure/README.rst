OpenTelemetry Resource detectors for Azure
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resource-detector-azure.svg
   :target: https://pypi.org/project/opentelemetry-resource-detector-azure/

This library contains OpenTelemetry `Resource Detectors <https://opentelemetry.io/docs/specs/otel/resource/sdk/#detecting-resource-information-from-the-environment>`_ for the following Azure resources:
 * `Azure Kubernetes Service <https://azure.microsoft.com/en-us/products/kubernetes-service>`_
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
    from opentelemetry.resource.detector.azure import (
        AzureAKSResourceDetector,
        AzureAppServiceResourceDetector,
        AzureVMResourceDetector,
    )
    from opentelemetry.sdk.resources import get_aggregated_resources


    trace.set_tracer_provider(
        TracerProvider(
            resource=get_aggregated_resources(
                [
                    AzureAKSResourceDetector(),
                    AzureAppServiceResourceDetector(),
                    AzureVMResourceDetector(),
                ]
            ),
        )
    )

Mappings
--------

The Azure Kubernetes Service Resource Detector reads the cluster resource ID from the
``CLUSTER_RESOURCE_ID`` environment variable or from a mounted ``aks-cluster-metadata``
ConfigMap at ``/etc/kubernetes/aks-cluster-metadata``. It sets the following Resource
Attributes:
 * ``cloud.platform`` set to ``azure_aks``.
 * ``cloud.provider`` set to ``azure``.
 * ``cloud.resource_id`` set to the full Azure Resource Manager cluster resource ID.
 * ``k8s.cluster.name`` set to the cluster name extracted from the resource ID.

The native AKS ConfigMap is named ``aks-cluster-metadata`` and contains a
``clusterResourceId`` key. It can be exposed to a pod as an environment variable:

.. code-block:: yaml

    env:
      - name: CLUSTER_RESOURCE_ID
        valueFrom:
          configMapKeyRef:
            name: aks-cluster-metadata
            key: clusterResourceId

Alternatively, mount the ConfigMap as a volume:

.. code-block:: yaml

    volumes:
      - name: aks-cluster-metadata
        configMap:
          name: aks-cluster-metadata
    volumeMounts:
      - name: aks-cluster-metadata
        mountPath: /etc/kubernetes/aks-cluster-metadata

Kubernetes resolves ConfigMap references within the pod's namespace. Because the native
ConfigMap is in ``kube-public``, copy it into the workload namespace or use tooling such
as an init container to expose its value through one of the supported locations.

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