# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Mapping

from opentelemetry.resourcedetector.gcp_resource_detector import (
    _faas,
    _gae,
    _gce,
    _gke,
    _metadata,
)
from opentelemetry.resourcedetector.gcp_resource_detector._constants import (
    ResourceAttributes,
)
from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.util.types import AttributeValue

_CLOUD_RUN_SERVICE_RESOURCE_ID = "//run.googleapis.com/projects/{project_id}/locations/{region}/services/{name}"
_CLOUD_RUN_JOB_RESOURCE_ID = "//run.googleapis.com/projects/{project_id}/locations/{region}/jobs/{name}"
_CLOUD_RUN_WORKER_POOL_RESOURCE_ID = "//run.googleapis.com/projects/{project_id}/locations/{region}/workerPools/{name}"
_CLOUD_FUNCTIONS_RESOURCE_ID = (
    "//cloudfunctions.googleapis.com/projects/{project_id}/locations/{region}/functions/{name}"
)


class GoogleCloudResourceDetector(ResourceDetector):
    def detect(self) -> Resource:
        # pylint: disable=too-many-return-statements
        if not _metadata.is_available():
            return Resource.get_empty()

        if _gke.on_gke():
            return _gke_resource()
        if _faas.on_cloud_run():
            return _cloud_run_resource()
        if _faas.on_cloud_functions():
            return _cloud_functions_resource()
        if _faas.on_cloud_run_job():
            return _cloud_run_job_resource()
        if _faas.on_cloud_run_worker_pool():
            return _cloud_run_worker_pool_resource()
        if _gae.on_app_engine():
            return _gae_resource()
        if _gce.on_gce():
            return _gce_resource()

        return Resource.get_empty()


def _gke_resource() -> Resource:
    zone_or_region = _gke.availability_zone_or_region()
    zone_or_region_key = (
        ResourceAttributes.CLOUD_AVAILABILITY_ZONE if zone_or_region.type == "zone" else ResourceAttributes.CLOUD_REGION
    )
    return _make_resource(
        {
            ResourceAttributes.CLOUD_PLATFORM_KEY: ResourceAttributes.GCP_KUBERNETES_ENGINE,
            zone_or_region_key: zone_or_region.value,
            ResourceAttributes.K8S_CLUSTER_NAME: _gke.cluster_name(),
            ResourceAttributes.HOST_ID: _gke.host_id(),
        }
    )


def _gce_resource() -> Resource:
    zone_and_region = _gce.availability_zone_and_region()
    return _make_resource(
        {
            ResourceAttributes.CLOUD_PLATFORM_KEY: ResourceAttributes.GCP_COMPUTE_ENGINE,
            ResourceAttributes.CLOUD_AVAILABILITY_ZONE: zone_and_region.zone,
            ResourceAttributes.CLOUD_REGION: zone_and_region.region,
            ResourceAttributes.HOST_TYPE: _gce.host_type(),
            ResourceAttributes.HOST_ID: _gce.host_id(),
            ResourceAttributes.HOST_NAME: _gce.host_name(),
        }
    )


def _cloud_run_resource() -> Resource:
    return _faas_resource(
        platform=ResourceAttributes.GCP_CLOUD_RUN,
        resource_id_template=_CLOUD_RUN_SERVICE_RESOURCE_ID,
        name=_faas.faas_name(),
        extra_attrs={ResourceAttributes.FAAS_VERSION: _faas.faas_version()},
    )


def _cloud_functions_resource() -> Resource:
    return _faas_resource(
        platform=ResourceAttributes.GCP_CLOUD_FUNCTIONS,
        resource_id_template=_CLOUD_FUNCTIONS_RESOURCE_ID,
        name=_faas.faas_name(),
        extra_attrs={ResourceAttributes.FAAS_VERSION: _faas.faas_version()},
    )


def _cloud_run_job_resource() -> Resource:
    extra_attrs: dict[str, AttributeValue] = {}
    if (execution := _faas.cloud_run_job_execution()) is not None:
        extra_attrs[ResourceAttributes.GCP_CLOUD_RUN_JOB_EXECUTION] = execution
    if (task_index := _faas.cloud_run_job_task_index()) is not None:
        extra_attrs[ResourceAttributes.GCP_CLOUD_RUN_JOB_TASK_INDEX] = task_index
    return _faas_resource(
        platform=ResourceAttributes.GCP_CLOUD_RUN,
        resource_id_template=_CLOUD_RUN_JOB_RESOURCE_ID,
        name=_faas.cloud_run_job_name(),
        extra_attrs=extra_attrs,
    )


def _cloud_run_worker_pool_resource() -> Resource:
    extra_attrs: dict[str, AttributeValue] = {}
    if (revision := _faas.cloud_run_worker_pool_revision()) is not None:
        extra_attrs[ResourceAttributes.FAAS_VERSION] = revision
    return _faas_resource(
        platform=ResourceAttributes.GCP_CLOUD_RUN,
        resource_id_template=_CLOUD_RUN_WORKER_POOL_RESOURCE_ID,
        name=_faas.cloud_run_worker_pool_name(),
        extra_attrs=extra_attrs,
    )


def _faas_resource(
    platform: str,
    resource_id_template: str,
    name: str,
    extra_attrs: Mapping[str, AttributeValue],
) -> Resource:
    project_id = _metadata.get_metadata()["project"]["projectId"]
    region = _faas.faas_cloud_region()
    attrs: dict[str, AttributeValue] = {
        ResourceAttributes.CLOUD_PLATFORM_KEY: platform,
        ResourceAttributes.FAAS_NAME: name,
        ResourceAttributes.FAAS_INSTANCE: _faas.faas_instance(),
        ResourceAttributes.CLOUD_REGION: region,
        **extra_attrs,
    }
    if project_id and region and name:
        attrs[ResourceAttributes.CLOUD_RESOURCE_ID] = resource_id_template.format(
            project_id=project_id,
            region=region,
            name=name,
        )
    return _make_resource(attrs)


def _gae_resource() -> Resource:
    if _gae.on_app_engine_standard():
        zone = _gae.standard_availability_zone()
        region = _gae.standard_cloud_region()
    else:
        zone_and_region = _gae.flex_availability_zone_and_region()
        zone = zone_and_region.zone
        region = zone_and_region.region

    faas_name = _gae.service_name()
    faas_version = _gae.service_version()
    faas_instance = _gae.service_instance()

    return _make_resource(
        {
            ResourceAttributes.CLOUD_PLATFORM_KEY: ResourceAttributes.GCP_APP_ENGINE,
            ResourceAttributes.FAAS_NAME: faas_name,
            ResourceAttributes.FAAS_VERSION: faas_version,
            ResourceAttributes.FAAS_INSTANCE: faas_instance,
            ResourceAttributes.CLOUD_AVAILABILITY_ZONE: zone,
            ResourceAttributes.CLOUD_REGION: region,
        }
    )


def _make_resource(attrs: Mapping[str, AttributeValue]) -> Resource:
    return Resource(
        {
            ResourceAttributes.CLOUD_PROVIDER: "gcp",
            ResourceAttributes.CLOUD_ACCOUNT_ID: _metadata.get_metadata()["project"]["projectId"],
            **attrs,
        }
    )


__all__ = ["GoogleCloudResourceDetector"]
