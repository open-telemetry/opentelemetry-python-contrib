# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Implementation in this file copied from
# https://github.com/GoogleCloudPlatform/opentelemetry-operations-go/blob/v1.8.0/detectors/gcp/faas.go

import os

from opentelemetry.resourcedetector.gcp_resource_detector import _metadata

_CLOUD_RUN_CONFIG_ENV = "K_CONFIGURATION"
_CLOUD_FUNCTION_TARGET_ENV = "FUNCTION_TARGET"
_FAAS_SERVICE_ENV = "K_SERVICE"
_FAAS_REVISION_ENV = "K_REVISION"


def on_cloud_run() -> bool:
    return _CLOUD_RUN_CONFIG_ENV in os.environ


def on_cloud_functions() -> bool:
    return _CLOUD_FUNCTION_TARGET_ENV in os.environ


def faas_name() -> str:
    """The name of the Cloud Run or Cloud Function.

    Check that on_cloud_run() or on_cloud_functions() is true before calling this, or it may
    throw exceptions.
    """
    return os.environ[_FAAS_SERVICE_ENV]


def faas_version() -> str:
    """The version/revision of the Cloud Run or Cloud Function.

    Check that on_cloud_run() or on_cloud_functions() is true before calling this, or it may
    throw exceptions.
    """
    return os.environ[_FAAS_REVISION_ENV]


def faas_instance() -> str:
    return str(_metadata.get_metadata()["instance"]["id"])


def faas_cloud_region() -> str:
    region = _metadata.get_metadata()["instance"]["region"]
    return region[region.rfind("/") + 1 :]
