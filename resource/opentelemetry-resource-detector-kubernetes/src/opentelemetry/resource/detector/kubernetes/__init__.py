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

import logging
import os
import socket

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import ResourceAttributes

logger = logging.getLogger(__name__)

_POD_ID_LENGTH = 36


class KubernetesResourceDetector(ResourceDetector):
    """Detects attribute values only available when the app is running on kubernetes
    container and returns a resource object.
    """

    def detect(self) -> "Resource":
        try:
            if (
                not os.environ.get("KUBERNETES_SERVICE_HOST")
                and not os.environ.get("KUBERNETES_SERVICE_PORT")
                and not os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS")
            ):
                raise RuntimeError(
                    "Missing Kubernetes default environment values therefore process is not on kubernetes."
                )

            pod_id = ""
            try:
                with open(
                    "/proc/self/mountinfo", encoding="utf8"
                ) as container_info_file:
                    for raw_line in container_info_file.readlines():
                        line = raw_line.strip()
                        # Subsequent IDs should be the same, exit if found one
                        if len(line) > _POD_ID_LENGTH and "pods" in line:
                            pod_id = line.split("pods/")[1][:_POD_ID_LENGTH]
                            break
            except FileNotFoundError as exception:
                logger.warning(
                    "Failed to get pod ID on kubernetes container: %s.",
                    exception,
                )

            return Resource(
                {
                    ResourceAttributes.CONTAINER_NAME: socket.gethostname(),
                    ResourceAttributes.K8S_POD_UID: pod_id,
                }
            )
        # pylint: disable=broad-except
        except Exception as exception:
            if self.raise_on_error:
                raise exception

            logger.warning("%s failed: %s", self.__class__.__name__, exception)
            return Resource.get_empty()
