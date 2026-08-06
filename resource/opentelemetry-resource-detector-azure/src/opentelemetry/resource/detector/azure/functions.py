# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from os import environ, getpid

from opentelemetry.resource.detector.azure._utils import (
    _get_azure_resource_uri,
    _is_on_functions,
)
from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)

from ._constants import (
    _FUNCTIONS_ATTRIBUTE_ENV_VARS,
    _REGION_NAME,
    _WEBSITE_SITE_NAME,
)


class AzureFunctionsResourceDetector(ResourceDetector):
    def detect(self) -> Resource:
        attributes = {}
        if _is_on_functions():
            website_site_name = environ.get(_WEBSITE_SITE_NAME)
            if website_site_name:
                attributes[ResourceAttributes.SERVICE_NAME] = website_site_name
            attributes[ResourceAttributes.PROCESS_PID] = getpid()
            attributes[ResourceAttributes.CLOUD_PROVIDER] = (
                CloudProviderValues.AZURE.value
            )
            attributes[ResourceAttributes.CLOUD_PLATFORM] = (
                CloudPlatformValues.AZURE_FUNCTIONS.value
            )
            cloud_region = environ.get(_REGION_NAME)
            if cloud_region:
                attributes[ResourceAttributes.CLOUD_REGION] = cloud_region
            azure_resource_uri = _get_azure_resource_uri()
            if azure_resource_uri:
                attributes[ResourceAttributes.CLOUD_RESOURCE_ID] = (
                    azure_resource_uri
                )
            for key, env_var in _FUNCTIONS_ATTRIBUTE_ENV_VARS.items():
                value = environ.get(env_var)
                if value:
                    if key == ResourceAttributes.FAAS_MAX_MEMORY:
                        try:
                            value = int(value)
                        except ValueError:
                            continue
                    attributes[key] = value

        return Resource(attributes)
