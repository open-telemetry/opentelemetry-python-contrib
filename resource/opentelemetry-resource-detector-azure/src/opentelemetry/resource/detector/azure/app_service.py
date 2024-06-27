# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Optional
from os import environ

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)
from opentelemetry.resource.detector.azure._utils import _get_azure_resource_uri

from ._constants import (
    _APP_SERVICE_ATTRIBUTE_ENV_VARS,
    _WEBSITE_SITE_NAME,
)

from opentelemetry.resource.detector.azure._utils import _is_on_functions


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
