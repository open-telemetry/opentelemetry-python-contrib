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

from json import loads
from logging import getLogger
from os import environ
from urllib.request import Request, urlopen
from urllib.error import URLError

from opentelemetry.sdk.resources import ResourceDetector, Resource
from opentelemetry.semconv.resource import ResourceAttributes, CloudPlatformValues, CloudProviderValues


# TODO: Remove when cloud resource id is no longer missing in Resource Attributes
_CLOUD_RESOURCE_ID_RESOURCE_ATTRIBUTE = "cloud.resource_id"
_AZURE_VM_METADATA_ENDPOINT = "http://169.254.169.254/metadata/instance/compute?api-version=2021-12-13&format=json"
_AZURE_VM_SCALE_SET_NAME_ATTRIBUTE = "azure.vm.scaleset.name"
_AZURE_VM_SKU_ATTRIBUTE = "azure.vm.sku"
_logger = getLogger(__name__)

EXPECTED_AZURE_AMS_ATTRIBUTES = [
    _AZURE_VM_SCALE_SET_NAME_ATTRIBUTE,
    _AZURE_VM_SKU_ATTRIBUTE,
    ResourceAttributes.CLOUD_PLATFORM,
    ResourceAttributes.CLOUD_PROVIDER,
    ResourceAttributes.CLOUD_REGION,
    _CLOUD_RESOURCE_ID_RESOURCE_ATTRIBUTE,
    ResourceAttributes.HOST_ID,
    ResourceAttributes.HOST_NAME,
    ResourceAttributes.HOST_TYPE,
    ResourceAttributes.OS_TYPE,
    ResourceAttributes.OS_VERSION,
    ResourceAttributes.SERVICE_INSTANCE_ID,
]

class AzureVMResourceDetector(ResourceDetector):
    # pylint: disable=no-self-use
    def detect(self) -> "Resource":
        attributes = {}
        metadata_json = _AzureVMMetadataServiceRequestor().get_azure_vm_metadata()
        if not metadata_json:
            return Resource(attributes)
        for attribute_key in EXPECTED_AZURE_AMS_ATTRIBUTES:
            attributes[attribute_key] = _AzureVMMetadataServiceRequestor().get_attribute_from_metadata(metadata_json, attribute_key)
        return Resource(attributes)

class _AzureVMMetadataServiceRequestor:
    def get_azure_vm_metadata(self):
        request = Request(_AZURE_VM_METADATA_ENDPOINT)
        request.add_header("Metadata", "True")
        try:
            response = urlopen(request).read()
            return loads(response)
        except URLError:
            # Not on Azure VM
            return None
        except Exception as e:
            _logger.exception("Failed to receive Azure VM metadata: %s", e)
            return None

    def get_attribute_from_metadata(self, metadata_json, attribute_key):
        ams_value = ""
        if attribute_key == _AZURE_VM_SCALE_SET_NAME_ATTRIBUTE:
            ams_value = metadata_json["vmScaleSetName"]
        elif attribute_key == _AZURE_VM_SKU_ATTRIBUTE:
            ams_value = metadata_json["sku"]
        elif attribute_key == ResourceAttributes.CLOUD_PLATFORM:
            ams_value = CloudPlatformValues.AZURE_VM.value
        elif attribute_key == ResourceAttributes.CLOUD_PROVIDER:
            ams_value = CloudProviderValues.AZURE.value
        elif attribute_key == ResourceAttributes.CLOUD_REGION:
            ams_value = metadata_json["location"]
        elif attribute_key == _CLOUD_RESOURCE_ID_RESOURCE_ATTRIBUTE:
            ams_value = metadata_json["resourceId"]
        elif attribute_key == ResourceAttributes.HOST_ID or \
            attribute_key == ResourceAttributes.SERVICE_INSTANCE_ID:
            ams_value = metadata_json["vmId"]
        elif attribute_key == ResourceAttributes.HOST_NAME:
            ams_value = metadata_json["name"]
        elif attribute_key == ResourceAttributes.HOST_TYPE:
            ams_value = metadata_json["vmSize"]
        elif attribute_key == ResourceAttributes.OS_TYPE:
            ams_value = metadata_json["osType"]
        elif attribute_key == ResourceAttributes.OS_VERSION:
            ams_value = metadata_json["version"]
        return ams_value
