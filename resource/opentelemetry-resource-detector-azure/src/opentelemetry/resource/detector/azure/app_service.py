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

from os import environ

from opentelemetry.sdk.resources import ResourceDetector, Resource
from opentelemetry.semconv.resource import ResourceAttributes, CloudPlatformValues, CloudProviderValues

_AZURE_APP_SERVICE_STAMP_RESOURCE_ATTRIBUTE = "azure.app.service.stamp"
# TODO: Remove once this resource attribute is no longer missing from SDK
_CLOUD_RESOURCE_ID_RESOURCE_ATTRIBUTE = "cloud.resource_id"
_REGION_NAME = "REGION_NAME"
_WEBSITE_HOME_STAMPNAME = "WEBSITE_HOME_STAMPNAME"
_WEBSITE_HOSTNAME = "WEBSITE_HOSTNAME"
_WEBSITE_INSTANCE_ID = "WEBSITE_INSTANCE_ID"
_WEBSITE_OWNER_NAME = "WEBSITE_OWNER_NAME"
_WEBSITE_RESOURCE_GROUP = "WEBSITE_RESOURCE_GROUP"
_WEBSITE_SITE_NAME = "WEBSITE_SITE_NAME"
_WEBSITE_SLOT_NAME = "WEBSITE_SLOT_NAME"


_APP_SERVICE_ATTRIBUTE_ENV_VARS = {
    ResourceAttributes.CLOUD_REGION: _REGION_NAME,
    ResourceAttributes.DEPLOYMENT_ENVIRONMENT: _WEBSITE_SLOT_NAME,
    ResourceAttributes.HOST_ID: _WEBSITE_HOSTNAME,
    ResourceAttributes.SERVICE_INSTANCE_ID: _WEBSITE_INSTANCE_ID,
    _AZURE_APP_SERVICE_STAMP_RESOURCE_ATTRIBUTE: _WEBSITE_HOME_STAMPNAME,
}

class AzureAppServiceResourceDetector(ResourceDetector):
    def detect(self) -> Resource:
        attributes = {}
        website_site_name = environ.get(_WEBSITE_SITE_NAME)
        if website_site_name:
            attributes[ResourceAttributes.SERVICE_NAME] = website_site_name
            attributes[ResourceAttributes.CLOUD_PROVIDER] = CloudProviderValues.AZURE.value
            attributes[ResourceAttributes.CLOUD_PLATFORM] = CloudPlatformValues.AZURE_APP_SERVICE.value

            azure_resource_uri = _get_azure_resource_uri(website_site_name)
            if azure_resource_uri:
                attributes[_CLOUD_RESOURCE_ID_RESOURCE_ATTRIBUTE] = azure_resource_uri
            for (key, env_var) in _APP_SERVICE_ATTRIBUTE_ENV_VARS.items():
                value = environ.get(env_var)
                if value:
                    attributes[key] = value

        return Resource(attributes)

def _get_azure_resource_uri(website_site_name):
    website_resource_group = environ.get(_WEBSITE_RESOURCE_GROUP)
    website_owner_name = environ.get(_WEBSITE_OWNER_NAME)

    subscription_id = website_owner_name
    if website_owner_name and '+' in website_owner_name:
        subscription_id = website_owner_name[0:website_owner_name.index('+')]

    if not (website_resource_group and subscription_id):
        return None

    return "/subscriptions/%s/resourceGroups/%s/providers/Microsoft.Web/sites/%s" % (
        subscription_id,
        website_resource_group,
        website_site_name,
    )
