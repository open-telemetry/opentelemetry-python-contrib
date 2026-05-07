# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from os import environ

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

from ._constants import _APP_SERVICE_ATTRIBUTE_ENV_VARS, _WEBSITE_SITE_NAME


class AzureAppServiceResourceDetector(ResourceDetector):
    def detect(self) -> Resource:
        attributes = {}
        website_site_name = environ.get(_WEBSITE_SITE_NAME)
        if website_site_name:
            # Functions resource detector takes priority with `service.name` and `cloud.platform`
            if not _is_on_functions():
                attributes[ResourceAttributes.SERVICE_NAME] = website_site_name
                attributes[ResourceAttributes.CLOUD_PLATFORM] = (
                    CloudPlatformValues.AZURE_APP_SERVICE.value
                )
            attributes[ResourceAttributes.CLOUD_PROVIDER] = (
                CloudProviderValues.AZURE.value
            )

            azure_resource_uri = _get_azure_resource_uri()
            if azure_resource_uri:
                attributes[ResourceAttributes.CLOUD_RESOURCE_ID] = (
                    azure_resource_uri
                )
            for key, env_var in _APP_SERVICE_ATTRIBUTE_ENV_VARS.items():
                value = environ.get(env_var)
                if value:
                    attributes[key] = value

        return Resource(attributes)
