# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
from functools import lru_cache
from typing import TypedDict, Union

import requests

_GCP_METADATA_URL = "http://metadata.google.internal/computeMetadata/v1/"
_INSTANCE = "instance"
_RECURSIVE_PARAMS = {"recursive": "true"}
_GCP_METADATA_URL_HEADER = {"Metadata-Flavor": "Google"}
# Use a shorter timeout for connection so we won't block much if it's unreachable
_TIMEOUT = (2, 5)

_logger = logging.getLogger(__name__)


class Project(TypedDict):
    projectId: str


Attributes = TypedDict(
    "Attributes", {"cluster-location": str, "cluster-name": str}, total=False
)


class Instance(TypedDict):
    attributes: Attributes
    # id can be an integer on GCE VMs or a string on other environments
    id: Union[int, str]
    machineType: str
    name: str
    region: str
    zone: str


class Metadata(TypedDict):
    instance: Instance
    project: Project


class MetadataAccessException(Exception):
    pass


@lru_cache(maxsize=None)
def get_metadata() -> Metadata:
    """Get all instance and project metadata from the metadata server

    Cached for the lifetime of the process.
    """
    try:
        res = requests.get(
            f"{_GCP_METADATA_URL}",
            params=_RECURSIVE_PARAMS,
            headers=_GCP_METADATA_URL_HEADER,
            timeout=_TIMEOUT,
        )
        res.raise_for_status()
        all_metadata = res.json()
    except requests.RequestException as err:
        raise MetadataAccessException() from err
    return all_metadata


@lru_cache(maxsize=None)
def is_available() -> bool:
    try:
        requests.get(
            f"{_GCP_METADATA_URL}{_INSTANCE}/",
            headers=_GCP_METADATA_URL_HEADER,
            timeout=_TIMEOUT,
        ).raise_for_status()
    except requests.RequestException:
        _logger.debug(
            "Failed to make request to metadata server, assuming it's not available",
            exc_info=True,
        )
        return False
    return True
