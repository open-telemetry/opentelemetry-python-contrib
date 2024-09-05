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
import platform
import socket

from opentelemetry.sdk.resources import ResourceDetector, Resource
from logging import getLogger

from opentelemetry.semconv.resource import ResourceAttributes

logger = getLogger(__name__)

def _get_host_name() -> str:
    return socket.gethostname()

def _get_host_arch() -> str:
    return platform.machine()
class HostResourceDetector(ResourceDetector):
    """
    The HostResourceDetector detects host resources using OpenTelemetry.
    """
    def detect(self) -> "Resource":
        try:
            host_name = _get_host_name()
            resource = Resource.get_empty()
            if host_name :
                resource = resource.merge(Resource({ResourceAttributes.HOST_NAME: host_name}))
            host_arch = _get_host_arch()
            if host_arch:
                resource = resource.merge(Resource({ResourceAttributes.HOST_ARCH: host_arch}))
            return resource
        except Exception as e:
            logger.warning(
                "%s Resource Detection failed silently: %s",
                self.__class__.__name__,
                e,
            )
            if self.raise_on_error:
                raise e
            return Resource.get_empty()
