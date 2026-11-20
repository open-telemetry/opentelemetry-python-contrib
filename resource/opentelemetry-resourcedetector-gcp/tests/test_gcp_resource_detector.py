# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from importlib.metadata import entry_points
from unittest.mock import Mock

import pytest
import requests

from opentelemetry.resourcedetector.gcp_resource_detector import (
    GoogleCloudResourceDetector,
    _metadata,
)


@pytest.fixture(name="reset_cache")
def fixture_reset_cache():
    yield
    _metadata.get_metadata.cache_clear()
    _metadata.is_available.cache_clear()


@pytest.fixture(name="fake_get")
def fixture_fake_get(monkeypatch: pytest.MonkeyPatch):
    mock = Mock()
    monkeypatch.setattr(requests, "get", mock)
    return mock


@pytest.fixture(name="fake_metadata")
def fixture_fake_metadata(fake_get: Mock):
    json = {"instance": {}, "project": {}}
    fake_get().json.return_value = json
    return json


# Reset stuff before every test
# pylint: disable=unused-argument
@pytest.fixture(autouse=True)
def autouse(reset_cache, fake_get, fake_metadata):
    pass


def test_detects_empty_when_not_available(snapshot, fake_get: Mock):
    fake_get.side_effect = requests.HTTPError()
    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


def test_detects_empty_as_fallback(snapshot):
    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


def test_detects_gce(snapshot, fake_metadata: _metadata.Metadata):
    fake_metadata.update(
        {
            "project": {"projectId": "fakeProject"},
            "instance": {
                "name": "fakeName",
                "hostname": "fakeName.c.fakeProject.internal",
                "id": "0087244a",
                "machineType": "fakeMachineType",
                "zone": "projects/233510669999/zones/us-east4-b",
                "attributes": {},
            },
        }
    )

    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


@pytest.mark.parametrize(
    ("created_by", "expected_mig_attrs"),
    (
        pytest.param(
            "projects/233510669999/zones/us-east4-b/instanceGroupManagers/my-zonal-mig",
            {
                "gcp.gce.instance_group_manager.name": "my-zonal-mig",
                "gcp.gce.instance_group_manager.zone": "us-east4-b",
            },
            id="zonal",
        ),
        pytest.param(
            "projects/233510669999/regions/us-east4/instanceGroupManagers/my-regional-mig",
            {
                "gcp.gce.instance_group_manager.name": "my-regional-mig",
                "gcp.gce.instance_group_manager.region": "us-east4",
            },
            id="regional",
        ),
        pytest.param(
            "projects/233510669999/zones/us-east4-b/otherResource/not-a-mig",
            {},
            id="non-mig",
        ),
    ),
)
def test_detects_gce_managed_instance_group(
    fake_metadata: _metadata.Metadata,
    created_by: str,
    expected_mig_attrs: dict[str, str],
):
    fake_metadata.update(
        {
            "project": {"projectId": "fakeProject"},
            "instance": {
                "name": "fakeName",
                "hostname": "fakeName.c.fakeProject.internal",
                "id": "0087244a",
                "machineType": "fakeMachineType",
                "zone": "projects/233510669999/zones/us-east4-b",
                "attributes": {"created-by": created_by},
            },
        }
    )

    assert dict(GoogleCloudResourceDetector().detect().attributes) == {
        "cloud.account.id": "fakeProject",
        "cloud.availability_zone": "us-east4-b",
        "cloud.platform": "gcp_compute_engine",
        "cloud.provider": "gcp",
        "cloud.region": "us-east4",
        "gcp.gce.instance.hostname": "fakeName.c.fakeProject.internal",
        "gcp.gce.instance.name": "fakeName",
        "host.id": "0087244a",
        "host.name": "fakeName",
        "host.type": "fakeMachineType",
        **expected_mig_attrs,
    }


@pytest.mark.parametrize(
    "cluster_location",
    (
        pytest.param("us-east4", id="regional"),
        pytest.param("us-east4-b", id="zonal"),
    ),
)
def test_detects_gke(
    cluster_location: str,
    snapshot,
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "fakehost")
    fake_metadata.update(
        {
            "project": {"projectId": "fakeProject"},
            "instance": {
                "name": "fakeName",
                "id": 12345,
                "machineType": "fakeMachineType",
                "zone": "projects/233510669999/zones/us-east4-b",
                # Plus some attributes
                "attributes": {
                    "cluster-name": "fakeClusterName",
                    "cluster-location": cluster_location,
                },
            },
        }
    )

    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


def test_detects_cloud_run(
    snapshot,
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("K_CONFIGURATION", "fake-configuration")
    monkeypatch.setenv("K_SERVICE", "fake-service")
    monkeypatch.setenv("K_REVISION", "fake-revision")
    fake_metadata.update(
        {
            "project": {"projectId": "fakeProject"},
            "instance": {
                # this will not be numeric on FaaS
                "id": "0087244a",
                "region": "projects/233510669999/regions/us-east4",
            },
        }
    )

    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


def test_detects_cloud_functions(
    snapshot,
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("FUNCTION_TARGET", "fake-function-target")
    # Note all K_* environment variables are set since Cloud Functions executes within Cloud
    # Run. This tests that the detector can differentiate between them
    monkeypatch.setenv("K_CONFIGURATION", "fake-configuration")
    monkeypatch.setenv("K_SERVICE", "fake-service")
    monkeypatch.setenv("K_REVISION", "fake-revision")
    fake_metadata.update(
        {
            "project": {"projectId": "fakeProject"},
            "instance": {
                # this will not be numeric on FaaS
                "id": "0087244a",
                "region": "projects/233510669999/regions/us-east4",
            },
        }
    )

    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


def test_detects_cloud_run_job(
    snapshot,
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CLOUD_RUN_JOB", "fake-job")
    monkeypatch.setenv("CLOUD_RUN_EXECUTION", "fake-job-exec")
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "0")
    fake_metadata.update(
        {
            "project": {"projectId": "fakeProject"},
            "instance": {
                "id": "0087244a",
                "region": "projects/233510669999/regions/us-east4",
            },
        }
    )

    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


def test_detects_cloud_run_job_without_optional_env_vars(
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CLOUD_RUN_JOB", "fake-job")
    monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "not-an-int")
    fake_metadata.update(
        {
            "project": {"projectId": "fakeProject"},
            "instance": {
                "id": "0087244a",
                "region": "projects/233510669999/regions/us-east4",
            },
        }
    )

    attrs = dict(GoogleCloudResourceDetector().detect().attributes)
    assert attrs == {
        "cloud.provider": "gcp",
        "cloud.account.id": "fakeProject",
        "cloud.platform": "gcp_cloud_run",
        "cloud.region": "us-east4",
        "cloud.resource_id": "//run.googleapis.com/projects/fakeProject/locations/us-east4/jobs/fake-job",
        "faas.name": "fake-job",
        "faas.instance": "0087244a",
    }


@pytest.mark.parametrize(
    ("env_vars", "project_id", "region"),
    (
        pytest.param(
            {"K_CONFIGURATION": "fake-configuration", "K_SERVICE": "fake-service", "K_REVISION": "fake-revision"},
            "",
            "projects/233510669999/regions/us-east4",
            id="cloud-run-empty-project",
        ),
        pytest.param(
            {"K_CONFIGURATION": "fake-configuration", "K_SERVICE": "fake-service", "K_REVISION": "fake-revision"},
            "fakeProject",
            "projects/233510669999/regions/",
            id="cloud-run-empty-region",
        ),
        pytest.param(
            {"K_CONFIGURATION": "fake-configuration", "K_SERVICE": "", "K_REVISION": "fake-revision"},
            "fakeProject",
            "projects/233510669999/regions/us-east4",
            id="cloud-run-empty-name",
        ),
        pytest.param(
            {"FUNCTION_TARGET": "fake-fn", "K_SERVICE": "fake-service", "K_REVISION": "fake-revision"},
            "fakeProject",
            "projects/233510669999/regions/",
            id="cloud-functions-empty-region",
        ),
        pytest.param(
            {"CLOUD_RUN_JOB": ""},
            "fakeProject",
            "projects/233510669999/regions/us-east4",
            id="cloud-run-job-empty-name",
        ),
    ),
)
def test_serverless_omits_cloud_resource_id_when_component_missing(
    env_vars: dict[str, str],
    project_id: str,
    region: str,
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    for key, val in env_vars.items():
        monkeypatch.setenv(key, val)
    fake_metadata.update(
        {
            "project": {"projectId": project_id},
            "instance": {
                "id": "0087244a",
                "region": region,
            },
        }
    )

    attrs = dict(GoogleCloudResourceDetector().detect().attributes)
    assert attrs["cloud.provider"] == "gcp"
    assert "cloud.resource_id" not in attrs


def test_detects_gae_standard(
    snapshot,
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("GAE_ENV", "standard")
    monkeypatch.setenv("GAE_SERVICE", "fake-service")
    monkeypatch.setenv("GAE_VERSION", "fake-version")
    monkeypatch.setenv("GAE_INSTANCE", "fake-instance")
    fake_metadata.update(
        {
            "project": {"projectId": "fakeProject"},
            "instance": {
                "region": "projects/233510669999/regions/us-east4",
                "zone": "us-east4-b",
            },
        }
    )

    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


def test_detects_gae_flex(
    snapshot,
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("GAE_SERVICE", "fake-service")
    monkeypatch.setenv("GAE_VERSION", "fake-version")
    monkeypatch.setenv("GAE_INSTANCE", "fake-instance")
    fake_metadata.update(
        {
            "project": {"projectId": "fakeProject"},
            "instance": {
                "zone": "projects/233510669999/zones/us-east4-b",
            },
        }
    )

    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


def test_entry_points():
    eps = entry_points(group="opentelemetry_resource_detector")
    ep_map = {ep.name: ep for ep in eps}
    assert "gcp" in ep_map
    assert "gcp_resource_detector" in ep_map
    assert ep_map["gcp"].load() is GoogleCloudResourceDetector
    assert ep_map["gcp_resource_detector"].load() is GoogleCloudResourceDetector
