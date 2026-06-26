# Copyright 2024 Google LLC
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

from unittest.mock import MagicMock

import pytest
from opentelemetry.resource.detector.gcp import _gae


# Reset stuff before every test
# pylint: disable=unused-argument
@pytest.fixture(autouse=True)
def autouse(fake_get_metadata):
    pass


def test_detects_on_gae(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAE_SERVICE", "fake-service")
    assert _gae.on_app_engine()


def test_detects_not_on_gae() -> None:
    assert not _gae.on_app_engine()


def test_detects_on_gae_standard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAE_ENV", "standard")
    assert _gae.on_app_engine_standard()


def test_detects_not_on_gae_standard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAE_SERVICE", "fake-service")
    assert _gae.on_app_engine()
    assert not _gae.on_app_engine_standard()


def test_detects_gae_service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAE_SERVICE", "fake-service")
    assert _gae.service_name() == "fake-service"


def test_detects_gae_service_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAE_VERSION", "fake-version")
    assert _gae.service_version() == "fake-version"


def test_detects_gae_service_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GAE_INSTANCE", "fake-instance")
    assert _gae.service_instance() == "fake-instance"


def test_detects_gae_flex_zone_and_region(
    fake_get_metadata: MagicMock,
) -> None:
    fake_get_metadata.return_value = {
        "instance": {"zone": "projects/233510669999/zones/us-east4-b"}
    }
    zone_and_region = _gae.flex_availability_zone_and_region()
    assert zone_and_region.zone == "us-east4-b"
    assert zone_and_region.region == "us-east4"


def test_gae_standard_zone(
    fake_get_metadata: MagicMock,
) -> None:
    fake_get_metadata.return_value = {
        "instance": {"zone": "projects/233510669999/zones/us15"}
    }
    assert _gae.standard_availability_zone() == "us15"


def test_gae_standard_region(
    fake_get_metadata: MagicMock,
) -> None:
    fake_get_metadata.return_value = {
        "instance": {"region": "projects/233510669999/regions/us-east4"}
    }
    assert _gae.standard_cloud_region() == "us-east4"
