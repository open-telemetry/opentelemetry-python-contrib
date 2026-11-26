# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
import re
from dataclasses import dataclass
from typing import Literal

from opentelemetry.resourcedetector.gcp_resource_detector import _metadata

# Format described in
# https://cloud.google.com/compute/docs/metadata/default-metadata-values#vm_instance_metadata
_ZONE_REGION_RE = re.compile(r"projects\/\d+\/zones\/(?P<zone>(?P<region>\w+-\w+)-\w+)")

# Format described in
# https://cloud.google.com/compute/docs/instance-groups/getting-info-about-migs#checking_if_a_vm_instance_is_part_of_a_mig
_CREATED_BY_MIG_RE = re.compile(
    r"^projects/[^/]+/(?P<type>zones|regions)/(?P<location>[^/]+)/instanceGroupManagers/(?P<name>[^/]+)$"
)

_logger = logging.getLogger(__name__)


def on_gce() -> bool:
    try:
        _metadata.get_metadata()["instance"]["machineType"]
    except (_metadata.MetadataAccessException, KeyError):
        _logger.debug(
            "Could not fetch metadata attribute instance/machineType, assuming not on GCE.",
            exc_info=True,
        )
        return False
    return True


def host_type() -> str:
    return _metadata.get_metadata()["instance"]["machineType"]


def host_id() -> str:
    return str(_metadata.get_metadata()["instance"]["id"])


def host_name() -> str:
    return _metadata.get_metadata()["instance"]["name"]


def instance_hostname() -> str | None:
    return _metadata.get_metadata()["instance"].get("hostname")


@dataclass
class ZoneAndRegion:
    zone: str
    region: str


def availability_zone_and_region() -> ZoneAndRegion:
    full_zone = _metadata.get_metadata()["instance"]["zone"]
    match = _ZONE_REGION_RE.search(full_zone)
    if not match:
        raise ValueError(
            f"zone was not in the expected format: projects/PROJECT_NUM/zones/COUNTRY-REGION-ZONE. Got {full_zone}"
        )

    return ZoneAndRegion(zone=match.group("zone"), region=match.group("region"))


@dataclass
class ManagedInstanceGroup:
    name: str
    location: str
    type: Literal["zone", "region"]


def managed_instance_group() -> ManagedInstanceGroup | None:
    attributes = _metadata.get_metadata()["instance"].get("attributes")
    if not attributes:
        return None
    created_by = attributes.get("created-by")
    if not created_by:
        return None
    match = _CREATED_BY_MIG_RE.match(created_by)
    if not match:
        return None
    loc_type: Literal["zone", "region"] = "zone" if match.group("type") == "zones" else "region"
    return ManagedInstanceGroup(
        name=match.group("name"),
        location=match.group("location"),
        type=loc_type,
    )
