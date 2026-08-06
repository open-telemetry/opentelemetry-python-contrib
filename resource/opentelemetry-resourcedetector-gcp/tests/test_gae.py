# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import pytest

from opentelemetry.resourcedetector.gcp_resource_detector import _gae


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
