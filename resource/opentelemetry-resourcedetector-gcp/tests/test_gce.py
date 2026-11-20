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
    fake_get_metadata.return_value = {"instance": {"zone": "projects/233510669999/zones/us-east4-b"}}
    zone_and_region = _gce.availability_zone_and_region()

    assert zone_and_region.zone == "us-east4-b"
    assert zone_and_region.region == "us-east4"


def test_throws_for_invalid_zone(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {"zone": ""}}

    with pytest.raises(ValueError, match="zone was not in the expected format"):
        _gce.availability_zone_and_region()


def test_detects_instance_hostname(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {"hostname": "fake.c.project.internal"}}
    assert _gce.instance_hostname() == "fake.c.project.internal"


def test_instance_hostname_missing(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {"instance": {}}
    assert _gce.instance_hostname() is None


def test_detects_zonal_managed_instance_group(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {
        "instance": {
            "attributes": {
                "created-by": "projects/123456789/zones/us-east4-b/instanceGroupManagers/my-zonal-mig",
            }
        }
    }
    assert _gce.managed_instance_group() == _gce.ManagedInstanceGroup(
        name="my-zonal-mig",
        location="us-east4-b",
        type="zone",
    )


def test_detects_regional_managed_instance_group(fake_get_metadata: MagicMock) -> None:
    fake_get_metadata.return_value = {
        "instance": {
            "attributes": {
                "created-by": "projects/123456789/regions/us-east4/instanceGroupManagers/my-regional-mig",
            }
        }
    }
    assert _gce.managed_instance_group() == _gce.ManagedInstanceGroup(
        name="my-regional-mig",
        location="us-east4",
        type="region",
    )


@pytest.mark.parametrize(
    "instance_meta",
    (
        pytest.param({}, id="no-attributes"),
        pytest.param({"attributes": {}}, id="no-created-by"),
        pytest.param({"attributes": {"created-by": ""}}, id="empty-created-by"),
        pytest.param(
            {"attributes": {"created-by": "projects/123456789/zones/us-east4-b/otherResource/foo"}},
            id="non-mig-created-by",
        ),
    ),
)
def test_managed_instance_group_returns_none(
    fake_get_metadata: MagicMock,
    instance_meta: dict,
) -> None:
    fake_get_metadata.return_value = {"instance": instance_meta}
    assert _gce.managed_instance_group() is None
