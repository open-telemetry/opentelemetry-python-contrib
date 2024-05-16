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

from opentelemetry.semconv.resource import ResourceAttributes

# cSpell:disable

# Azure Kubernetes

_AKS_ARM_NAMESPACE_ID = "AKS_ARM_NAMESPACE_ID"

# AppService

_AZURE_APP_SERVICE_STAMP_RESOURCE_ATTRIBUTE = "azure.app.service.stamp"
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

# Functions

_FUNCTIONS_WORKER_RUNTIME = "FUNCTIONS_WORKER_RUNTIME"
_WEBSITE_MEMORY_LIMIT_MB = "WEBSITE_MEMORY_LIMIT_MB"

_FUNCTIONS_ATTRIBUTE_ENV_VARS = {
    ResourceAttributes.FAAS_INSTANCE: _WEBSITE_INSTANCE_ID,
    ResourceAttributes.FAAS_MAX_MEMORY: _WEBSITE_MEMORY_LIMIT_MB,
}

# Vm

_AZURE_VM_METADATA_ENDPOINT = "http://169.254.169.254/metadata/instance/compute?api-version=2021-12-13&format=json"
_AZURE_VM_SCALE_SET_NAME_ATTRIBUTE = "azure.vm.scaleset.name"
_AZURE_VM_SKU_ATTRIBUTE = "azure.vm.sku"

_EXPECTED_AZURE_AMS_ATTRIBUTES = [
    _AZURE_VM_SCALE_SET_NAME_ATTRIBUTE,
    _AZURE_VM_SKU_ATTRIBUTE,
    ResourceAttributes.CLOUD_PLATFORM,
    ResourceAttributes.CLOUD_PROVIDER,
    ResourceAttributes.CLOUD_REGION,
    ResourceAttributes.CLOUD_RESOURCE_ID,
    ResourceAttributes.HOST_ID,
    ResourceAttributes.HOST_NAME,
    ResourceAttributes.HOST_TYPE,
    ResourceAttributes.OS_TYPE,
    ResourceAttributes.OS_VERSION,
    ResourceAttributes.SERVICE_INSTANCE_ID,
]

# cSpell:enable
