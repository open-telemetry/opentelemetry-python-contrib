# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from logging import getLogger
from os import environ
from pathlib import Path
from typing import Optional

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)

from ._constants import (
    _AKS_CLUSTER_RESOURCE_ID,
    _AKS_CLUSTER_RESOURCE_ID_KEY,
    _AKS_METADATA_FILE_PATH,
)

_logger = getLogger(__name__)


def _extract_cluster_name(resource_id: str) -> Optional[str]:
    segments = resource_id.split("/")
    for index, segment in enumerate(segments):
        if segment.lower() == "managedclusters" and index < len(segments) - 1:
            return segments[index + 1]
    return segments[-1] or None


def _parse_aks_metadata(content: str) -> Optional[str]:
    keyed_resource_id: Optional[str] = None
    bare_values: list[str] = []

    for line in content.splitlines():
        stripped_line = line.strip().lstrip("\ufeff")
        if not stripped_line or stripped_line.startswith("#"):
            continue

        key, separator, value = stripped_line.partition("=")
        if not separator:
            bare_values.append(stripped_line)
        elif key.strip() == _AKS_CLUSTER_RESOURCE_ID_KEY and value.strip():
            keyed_resource_id = value.strip()

    if keyed_resource_id:
        return keyed_resource_id
    if len(bare_values) == 1:
        return bare_values[0]
    return None


def _get_aks_metadata_from_file() -> Optional[str]:
    metadata_path = Path(_AKS_METADATA_FILE_PATH)
    try:
        if metadata_path.is_dir():
            metadata_path = metadata_path / _AKS_CLUSTER_RESOURCE_ID_KEY
        content = metadata_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        _logger.debug(
            "Failed to read AKS metadata from %s",
            metadata_path,
            exc_info=True,
        )
        return None

    return _parse_aks_metadata(content)


class AzureAKSResourceDetector(ResourceDetector):
    def detect(self) -> Resource:
        resource_id = (
            environ.get(_AKS_CLUSTER_RESOURCE_ID)
            or _get_aks_metadata_from_file()
        )
        if not resource_id:
            return Resource({})

        attributes = {
            ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AZURE.value,
            ResourceAttributes.CLOUD_PLATFORM: (
                CloudPlatformValues.AZURE_AKS.value
            ),
            ResourceAttributes.CLOUD_RESOURCE_ID: resource_id,
        }
        cluster_name = _extract_cluster_name(resource_id)
        if cluster_name:
            attributes[ResourceAttributes.K8S_CLUSTER_NAME] = cluster_name

        return Resource(attributes)
