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

import json
import logging
import os
import re
import socket
from urllib.request import Request, urlopen

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)

logger = logging.getLogger(__name__)

_CONTAINER_ID_LENGTH = 64


class AwsEcsResourceDetector(ResourceDetector):
    """Detects attribute values only available when the app is running on AWS
    Elastic Container Service (ECS) and returns them in a Resource.
    """

    def detect(self) -> "Resource":
        try:
            if not os.environ.get(
                "ECS_CONTAINER_METADATA_URI"
            ) and not os.environ.get("ECS_CONTAINER_METADATA_URI_V4"):
                raise RuntimeError(
                    "Missing ECS_CONTAINER_METADATA_URI therefore process is not on ECS."
                )

            container_id = ""
            try:
                with open(
                    "/proc/self/cgroup", encoding="utf8"
                ) as container_info_file:
                    for raw_line in container_info_file.readlines():
                        line = raw_line.strip()
                        # Subsequent IDs should be the same, exit if found one
                        if len(line) > _CONTAINER_ID_LENGTH:
                            container_id = line[-_CONTAINER_ID_LENGTH:]
                            break
            except FileNotFoundError as exception:
                logger.warning(
                    "Failed to get container ID on ECS: %s.", exception
                )

            base_resource = Resource(
                {
                    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS.value,
                    ResourceAttributes.CLOUD_PLATFORM: CloudPlatformValues.AWS_ECS.value,
                    ResourceAttributes.CONTAINER_NAME: socket.gethostname(),
                    ResourceAttributes.CONTAINER_ID: container_id,
                }
            )

            metadata_v4_endpoint = os.environ.get(
                "ECS_CONTAINER_METADATA_URI_V4"
            )

            if not metadata_v4_endpoint:
                return base_resource

            # Returns https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-metadata-endpoint-v4.html#task-metadata-endpoint-v4-response
            metadata_container = json.loads(_http_get(metadata_v4_endpoint))
            metadata_task = json.loads(
                _http_get(f"{metadata_v4_endpoint}/task")
            )

            task_arn = metadata_task["TaskARN"]
            base_arn = task_arn[0 : task_arn.rindex(":")]  # noqa
            cluster: str = metadata_task["Cluster"]
            cluster_arn = (
                cluster
                if cluster.startswith("arn:")
                else f"{base_arn}:cluster/{cluster}"
            )

            logs_resource = _get_logs_resource(metadata_container)

            return base_resource.merge(logs_resource).merge(
                Resource(
                    {
                        ResourceAttributes.AWS_ECS_CONTAINER_ARN: metadata_container[
                            "ContainerARN"
                        ],
                        ResourceAttributes.AWS_ECS_CLUSTER_ARN: cluster_arn,
                        ResourceAttributes.AWS_ECS_LAUNCHTYPE: metadata_task[
                            "LaunchType"
                        ].lower(),
                        ResourceAttributes.AWS_ECS_TASK_ARN: task_arn,
                        ResourceAttributes.AWS_ECS_TASK_FAMILY: metadata_task[
                            "Family"
                        ],
                        ResourceAttributes.AWS_ECS_TASK_REVISION: metadata_task[
                            "Revision"
                        ],
                    }
                )
            )
        # pylint: disable=broad-except
        except Exception as exception:
            if self.raise_on_error:
                raise exception

            logger.warning("%s failed: %s", self.__class__.__name__, exception)
            return Resource.get_empty()


def _get_logs_resource(metadata_container):
    if metadata_container.get("LogDriver") == "awslogs":
        log_options = metadata_container.get("LogOptions")
        if log_options:
            logs_region = log_options.get("awslogs-region")
            logs_group_name = log_options.get("awslogs-group")
            logs_stream_name = log_options.get("awslogs-stream")

            container_arn = metadata_container["ContainerARN"]

            if not logs_region:
                aws_region_match = re.match(
                    r"arn:aws:ecs:([^:]+):.*", container_arn
                )
                if aws_region_match:
                    logs_region = aws_region_match.group(1)

                else:
                    logger.warning("Cannot parse AWS region out of ECS ARN")

            # We need to retrieve the account ID from some other ARN to create the
            # log-group and log-stream ARNs
            aws_account = None
            aws_account_match = re.match(
                r"arn:aws:ecs:[^:]+:([^:]+):.*", container_arn
            )
            if aws_account_match:
                aws_account = aws_account_match.group(1)

            logs_group_arn = None
            logs_stream_arn = None
            if logs_region and aws_account:
                if logs_group_name:
                    logs_group_arn = f"arn:aws:logs:{logs_region}:{aws_account}:log-group:{logs_group_name}"

                if logs_stream_name:
                    logs_stream_arn = f"arn:aws:logs:{logs_region}:{aws_account}:log-group:{logs_group_name}:log-stream:{logs_stream_name}"

            return Resource(
                {
                    ResourceAttributes.AWS_LOG_GROUP_NAMES: [logs_group_name],
                    ResourceAttributes.AWS_LOG_GROUP_ARNS: [logs_group_arn],
                    ResourceAttributes.AWS_LOG_STREAM_NAMES: [
                        logs_stream_name
                    ],
                    ResourceAttributes.AWS_LOG_STREAM_ARNS: [logs_stream_arn],
                }
            )

        logger.warning(
            "The metadata endpoint v4 has returned 'awslogs' as 'LogDriver', but there is no 'LogOptions' data"
        )

    return Resource.get_empty()


def _http_get(url):
    with urlopen(
        Request(url, method="GET"),
        timeout=5,
    ) as response:
        return response.read().decode("utf-8")
