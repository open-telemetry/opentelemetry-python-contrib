# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os
from dataclasses import dataclass
from typing import Literal

from opentelemetry.resource.detector.gcp import (
    _gce,
    _metadata,
)

KUBERNETES_SERVICE_HOST_ENV = "KUBERNETES_SERVICE_HOST"


def on_gke() -> bool:
    return os.environ.get(KUBERNETES_SERVICE_HOST_ENV) is not None


def host_id() -> str:
    return _gce.host_id()


def cluster_name() -> str:
    return _metadata.get_metadata()["instance"]["attributes"]["cluster-name"]


@dataclass
class ZoneOrRegion:
    type: Literal["zone", "region"]
    value: str


def availability_zone_or_region() -> ZoneOrRegion:
    cluster_location = _metadata.get_metadata()["instance"]["attributes"][
        "cluster-location"
    ]
    hyphen_count = cluster_location.count("-")
    if hyphen_count == 1:
        return ZoneOrRegion(type="region", value=cluster_location)
    if hyphen_count == 2:
        return ZoneOrRegion(type="zone", value=cluster_location)
    raise ValueError(
        f"unrecognized format for cluster location: {cluster_location}"
    )
