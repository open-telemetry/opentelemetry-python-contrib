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

import os

from opentelemetry.resource.detector.azure._constants import (
    _AKS_ARM_NAMESPACE_ID,
    _FUNCTIONS_WORKER_RUNTIME,
    _WEBSITE_SITE_NAME,
)

def _is_on_aks() -> bool:
    return os.environ.get(_AKS_ARM_NAMESPACE_ID) is not None

def _is_on_app_service() -> bool:
    return os.environ.get(_WEBSITE_SITE_NAME) is not None

def _is_on_functions() -> bool:
    return os.environ.get(_FUNCTIONS_WORKER_RUNTIME) is not None

def _can_ignore_vm_detect() -> bool:
    return _is_on_aks() or _is_on_app_service() or _is_on_functions()
