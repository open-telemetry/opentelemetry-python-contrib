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
                "id": "0087244a",
                "machineType": "fakeMachineType",
                "zone": "projects/233510669999/zones/us-east4-b",
                "attributes": {},
            },
        }
    )

    assert dict(GoogleCloudResourceDetector().detect().attributes) == snapshot


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
    # Cloud Functions (1st gen) sets FUNCTION_TARGET, K_SERVICE, and K_REVISION,
    # without K_CONFIGURATION (which is only set on Cloud Run-backed services).
    monkeypatch.setenv("FUNCTION_TARGET", "fake-function-target")
    monkeypatch.setenv("FUNCTION_SIGNATURE_TYPE", "http")
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


def test_detects_cloud_run_function(
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    # Cloud Run functions (including functions deployed via `gcloud run deploy --function`
    # and Cloud Functions 2nd gen) set both K_CONFIGURATION and FUNCTION_TARGET/FUNCTION_SIGNATURE_TYPE.
    # They run as Cloud Run services and should detect as gcp_cloud_run with a run.googleapis.com resource ID.
    monkeypatch.setenv("FUNCTION_TARGET", "fake-function-target")
    monkeypatch.setenv("FUNCTION_SIGNATURE_TYPE", "http")
    monkeypatch.setenv("K_CONFIGURATION", "fake-configuration")
    monkeypatch.setenv("K_SERVICE", "fake-service")
    monkeypatch.setenv("K_REVISION", "fake-revision")
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
        "cloud.resource_id": "//run.googleapis.com/projects/fakeProject/locations/us-east4/services/fake-service",
        "faas.instance": "0087244a",
        "faas.name": "fake-service",
        "faas.version": "fake-revision",
    }


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


def test_detects_cloud_run_worker_pool(
    snapshot,
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CLOUD_RUN_WORKER_POOL", "fake-worker-pool")
    monkeypatch.setenv("CLOUD_RUN_REVISION", "fake-worker-pool-00001")
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


def test_detects_cloud_run_worker_pool_without_optional_env_vars(
    fake_metadata: _metadata.Metadata,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CLOUD_RUN_WORKER_POOL", "fake-worker-pool")
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
        "cloud.resource_id": "//run.googleapis.com/projects/fakeProject/locations/us-east4/workerPools/fake-worker-pool",
        "faas.name": "fake-worker-pool",
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
        pytest.param(
            {"CLOUD_RUN_WORKER_POOL": ""},
            "fakeProject",
            "projects/233510669999/regions/us-east4",
            id="cloud-run-worker-pool-empty-name",
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
