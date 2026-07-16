# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Implementation in this file copied from
# https://github.com/GoogleCloudPlatform/opentelemetry-operations-go/blob/v1.8.0/detectors/gcp/app_engine.go

import os

from opentelemetry.resource.detector.gcp import (
    _faas,
    _gce,
    _metadata,
)

_GAE_SERVICE_ENV = "GAE_SERVICE"
_GAE_VERSION_ENV = "GAE_VERSION"
_GAE_INSTANCE_ENV = "GAE_INSTANCE"
_GAE_ENV = "GAE_ENV"
_GAE_STANDARD = "standard"


def on_app_engine_standard() -> bool:
    return os.environ.get(_GAE_ENV) == _GAE_STANDARD


def on_app_engine() -> bool:
    return _GAE_SERVICE_ENV in os.environ


def service_name() -> str:
    """The service name of the app engine service.

    Check that ``on_app_engine()`` is true before calling this, or it may throw exceptions.
    """
    return os.environ[_GAE_SERVICE_ENV]


def service_version() -> str:
    """The service version of the app engine service.

    Check that ``on_app_engine()`` is true before calling this, or it may throw exceptions.
    """
    return os.environ[_GAE_VERSION_ENV]


def service_instance() -> str:
    """The service instance of the app engine service.

    Check that ``on_app_engine()`` is true before calling this, or it may throw exceptions.
    """
    return os.environ[_GAE_INSTANCE_ENV]


def flex_availability_zone_and_region() -> _gce.ZoneAndRegion:
    """The zone and region in which this program is running.

    Check that ``on_app_engine()`` is true before calling this, or it may throw exceptions.
    """
    return _gce.availability_zone_and_region()


def standard_availability_zone() -> str:
    """The zone the app engine service is running in.

    Check that ``on_app_engine_standard()`` is true before calling this, or it may throw exceptions.
    """
    zone = _metadata.get_metadata()["instance"]["zone"]
    # zone is of the form "projects/233510669999/zones/us15"
    return zone[zone.rfind("/") + 1 :]


def standard_cloud_region() -> str:
    """The region the app engine service is running in.

    Check that ``on_app_engine_standard()`` is true before calling this, or it may throw exceptions.
    """
    return _faas.faas_cloud_region()
