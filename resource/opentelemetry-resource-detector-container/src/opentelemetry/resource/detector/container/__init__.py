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

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import ResourceAttributes

logger = logging.getLogger(__name__)
DEFAULT_CGROUP_V1_PATH = "/proc/self/cgroup"
DEFAULT_CGROUP_V2_PATH = "/proc/self/mountinfo"
CONTAINER_ID_LENGTH = 64


def _get_container_id_v1():
    container_id = None
    try:
        with open(
            DEFAULT_CGROUP_V1_PATH, encoding="utf8"
        ) as container_info_file:
            for raw_line in container_info_file.readlines():
                line = raw_line.strip()
                if len(line) > CONTAINER_ID_LENGTH:
                    container_id = line[-CONTAINER_ID_LENGTH:]
                    break
    except FileNotFoundError as exception:
        logger.warning(
            f"Failed to get container id. Exception: {exception}"
        )
    return container_id


def _get_container_id_v2():
    container_id = None
    try:
        with open(
            DEFAULT_CGROUP_V2_PATH, encoding="utf8"
        ) as container_info_file:
            for raw_line in container_info_file.readlines():
                line = raw_line.strip()
                if "hostname" in line:
                    container_id_list = [
                        id
                        for id in line.split("/")
                        if len(id) == CONTAINER_ID_LENGTH
                    ]
                    if len(container_id_list) > 0:
                        container_id = container_id_list[0]
                        break

    except FileNotFoundError as exception:
        logger.warning(
            f"Failed to get container id. Exception: {exception}"
        )
    return container_id


class ContainerResourceDetector(ResourceDetector):
    """Detects container.id only available when app is running inside the
    docker container and return it in a Resource
    """

    def detect(self) -> "Resource":
        try:
            container_id = _get_container_id_v1() or _get_container_id_v2()
            resource = Resource.get_empty()
            if container_id:
                resource = resource.merge(
                    Resource({ResourceAttributes.CONTAINER_ID: container_id})
                )
            return resource

        except Exception as exception:
            logger.warning(
                "%s Resource Detection failed silently: %s",
                self.__class__.__name__,
                exception,
            )
            if self.raise_on_error:
                raise exception
            return Resource.get_empty()
