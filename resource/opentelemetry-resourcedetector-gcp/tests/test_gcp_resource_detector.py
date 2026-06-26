# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import Mock

import pytest
import requests
from opentelemetry.resource.detector.gcp import (
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
