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

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import ResourceAttributes

logger = logging.getLogger(__name__)
DEFAULT_CGROUP_V1_PATH = "/proc/self/mountinfo"
DEFAULT_CGROUP_V2_PATH = "/proc/self/cgroup"
KUBERNETES_SECRET_PATH = "/var/run/secrets/kubernetes.io"
_POD_ID_LENGTH = 36
_CONTAINER_ID_LENGTH = 64


def is_container_on_kubernetes() -> bool:
    # Kubernetes manages the /etc/hosts file inside the pods' containers,
    # using a distinctive header, see https://github.com/kubernetes/kubernetes/commit/fd72938dd569bd041f11a76eecfe9b8b4bcf5ae8
    with open("/etc/hosts", "r", encoding="utf8") as hosts_file:
        first_line = hosts_file.readline()
        return "Kubernetes" in first_line or os.path.exists(
            KUBERNETES_SECRET_PATH
        )


def get_kubenertes_pod_uid_v1():
    pod_id = None
    try:
        with open(
            DEFAULT_CGROUP_V1_PATH, encoding="utf8"
        ) as container_info_file:
            for raw_line in container_info_file.readlines():
                line = raw_line.strip()
                # Subsequent IDs should be the same, exit if found one
                if len(line) > _POD_ID_LENGTH and "/pods/" in line:
                    pod_id = line.split("/pods/")[1][:_POD_ID_LENGTH]
                    break
    except FileNotFoundError as exception:
        logger.warning("Failed to get k8 id. Exception: %s}", exception)
    return pod_id


def get_kubenertes_pod_uid_v2():
    pod_id = None
    try:
        with open(
            DEFAULT_CGROUP_V2_PATH, encoding="utf8"
        ) as container_info_file:
            for raw_line in container_info_file.readlines():
                line = raw_line.strip()
                # Subsequent IDs should be the same, exit if found one
                if len(line) > _CONTAINER_ID_LENGTH:
                    line_info = line.split("/")
                    if (
                        len(line_info) > 2
                        and line_info[-2][:3] == "pod"
                        and len(line_info[-2]) == _POD_ID_LENGTH + 3
                    ):
                        pod_id = line_info[-2][3 : 3 + _POD_ID_LENGTH]
                    else:
                        pod_id = line_info[-2]
                    break
    except FileNotFoundError as exception:
        logger.warning("Failed to get k8 id. Exception: %s}", exception)
    return pod_id


class KubernetesResourceDetector(ResourceDetector):
    """Detects attribute values only available when the app is running on kubernetes
    container and returns a resource object.
    """

    def detect(self) -> "Resource":
        try:
            pod_resource = Resource.get_empty()
            if is_container_on_kubernetes():
                pod_uid = (
                    get_kubenertes_pod_uid_v1() or get_kubenertes_pod_uid_v2()
                )
                if pod_uid:
                    pod_resource = pod_resource.merge(
                        Resource(
                            {
                                ResourceAttributes.K8S_POD_UID: pod_uid,
                            }
                        )
                    )
            else:
                logger.warning(
                    "Could not confirm process is running on kubernetes cluster."
                )
            return pod_resource

        # pylint: disable=broad-except
        except Exception as exception:
            if self.raise_on_error:
                raise exception

            logger.warning(
                "Failed to get pod ID on kubernetes cluster: %s.",
                exception,
            )
            return Resource.get_empty()
