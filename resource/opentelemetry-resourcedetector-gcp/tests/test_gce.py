# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import pytest

from opentelemetry.resourcedetector.gcp_resource_detector import (
    _gce,
    _metadata,
)


# Reset stuff before every test
# pylint: disable=unused-argument
@pytest.fixture(autouse=True)
def autouse(fake_get_metadata):
    pass


def test_detects_on_gce() -> None:
    assert _gce.on_gce()


def test_detects_not_on_gce(fake_get_metadata: MagicMock) -> None:
    # when the metadata server is not accessible
    fake_get_metadata.side_effect = _metadata.MetadataAccessException()
    assert not _gce.on_gce()

    # when the metadata server doesn't have the expected structure
    fake_get_metadata.return_value = {}
    assert not _gce.on_gce()


def test_detects_host_type(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {"machineType": "fake"}}
    assert _gce.host_type() == "fake"


def test_detects_host_id(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {"id": 12345}}
    assert _gce.host_id() == "12345"


def test_detects_host_name(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {"name": "fake"}}
    assert _gce.host_name() == "fake"


def test_detects_zone_and_region(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {
        "instance": {"zone": "projects/233510669999/zones/us-east4-b"}
    }
    zone_and_region = _gce.availability_zone_and_region()

    assert zone_and_region.zone == "us-east4-b"
    assert zone_and_region.region == "us-east4"


def test_throws_for_invalid_zone(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {"zone": ""}}

    with pytest.raises(
        ValueError, match="zone was not in the expected format"
    ):
        _gce.availability_zone_and_region()
