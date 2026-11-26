# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Implementation in this file adapted from
# https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/detectors/gcp/internal/faas.go

import logging
import os

from opentelemetry.resourcedetector.gcp_resource_detector import _metadata

_CLOUD_RUN_CONFIG_ENV = "K_CONFIGURATION"
_CLOUD_FUNCTION_TARGET_ENV = "FUNCTION_TARGET"
_CLOUD_RUN_JOB_ENV = "CLOUD_RUN_JOB"
_CLOUD_RUN_EXECUTION_ENV = "CLOUD_RUN_EXECUTION"
_CLOUD_RUN_TASK_INDEX_ENV = "CLOUD_RUN_TASK_INDEX"
_CLOUD_RUN_WORKER_POOL_ENV = "CLOUD_RUN_WORKER_POOL"
_CLOUD_RUN_REVISION_ENV = "CLOUD_RUN_REVISION"
_CLOUD_RUN_INSTANCE_ENV = "CLOUD_RUN_INSTANCE"
_FAAS_SERVICE_ENV = "K_SERVICE"
_FAAS_REVISION_ENV = "K_REVISION"

_logger = logging.getLogger(__name__)


def on_cloud_run() -> bool:
    return _CLOUD_RUN_CONFIG_ENV in os.environ


def on_cloud_functions() -> bool:
    return _CLOUD_FUNCTION_TARGET_ENV in os.environ


def on_cloud_run_job() -> bool:
    return _CLOUD_RUN_JOB_ENV in os.environ


def on_cloud_run_worker_pool() -> bool:
    return _CLOUD_RUN_WORKER_POOL_ENV in os.environ


def on_cloud_run_instance() -> bool:
    return _CLOUD_RUN_INSTANCE_ENV in os.environ


def faas_name() -> str:
    """The name of the Cloud Run or Cloud Function.

    Check that on_cloud_run() or on_cloud_functions() is true before calling this, or it may
    throw exceptions.
    """
    return os.environ[_FAAS_SERVICE_ENV]


def cloud_run_job_name() -> str:
    """The name of the Cloud Run job.

    Check that on_cloud_run_job() is true before calling this, or it may throw exceptions.
    """
    return os.environ[_CLOUD_RUN_JOB_ENV]


def cloud_run_job_execution() -> str | None:
    return os.environ.get(_CLOUD_RUN_EXECUTION_ENV)


def cloud_run_job_task_index() -> int | None:
    raw_index = os.environ.get(_CLOUD_RUN_TASK_INDEX_ENV)
    if raw_index is None:
        return None
    try:
        return int(raw_index)
    except ValueError:
        _logger.warning(
            "Can't parse GCP Cloud Run job task index (%s): %r",
            _CLOUD_RUN_TASK_INDEX_ENV,
            raw_index,
        )
        return None


def cloud_run_worker_pool_name() -> str:
    """The name of the Cloud Run worker pool.

    Check that on_cloud_run_worker_pool() is true before calling this, or it may throw exceptions.
    """
    return os.environ[_CLOUD_RUN_WORKER_POOL_ENV]


def cloud_run_worker_pool_revision() -> str | None:
    return os.environ.get(_CLOUD_RUN_REVISION_ENV)


def cloud_run_instance_name() -> str:
    """The name of the Cloud Run instance.

    Check that on_cloud_run_instance() is true before calling this, or it may throw exceptions.
    """
    return os.environ[_CLOUD_RUN_INSTANCE_ENV]


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
