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

from os import environ, getpid

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
from opentelemetry.resource.detector.azure._utils import (
    _get_azure_resource_uri,
    _is_on_functions,
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

