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

import unittest
from collections import OrderedDict
from os.path import dirname, join
from unittest.mock import mock_open, patch

from opentelemetry.sdk.extension.aws.resource.ecs import (  # pylint: disable=no-name-in-module
    AwsEcsResourceDetector,
)
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)

MockEcsResourceAttributes = {
    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS.value,
    ResourceAttributes.CLOUD_PLATFORM: CloudPlatformValues.AWS_ECS.value,
    ResourceAttributes.CONTAINER_NAME: "mock-container-name",
    ResourceAttributes.CONTAINER_ID: "a4d00c9dd675d67f866c786181419e1b44832d4696780152e61afd44a3e02856",
}


def _read_file(filename: str) -> str:
    with open(
        join(dirname(__file__), "ecs", filename), encoding="utf-8"
    ) as file:
        return file.read()


MetadataV4Uri = "mock-uri-4"


MetadataV4ContainerResponseEc2 = _read_file(
    "metadatav4-response-container-ec2.json"
)


MetadataV4TaskResponseEc2 = _read_file("metadatav4-response-task-ec2.json")


MetadataV4ContainerResponseFargate = _read_file(
    "metadatav4-response-container-fargate.json"
)


MetadataV4TaskResponseFargate = _read_file(
    "metadatav4-response-task-fargate.json"
)


def _http_get_function_ec2(url: str, *args, **kwargs) -> str:
    if url == MetadataV4Uri:
        return MetadataV4ContainerResponseEc2
    if url == f"{MetadataV4Uri}/task":
        return MetadataV4TaskResponseEc2
    return None


def _http_get_function_fargate(url: str, *args, **kwargs) -> str:
    if url == MetadataV4Uri:
        return MetadataV4ContainerResponseFargate
    if url == f"{MetadataV4Uri}/task":
        return MetadataV4TaskResponseFargate
    return None


class AwsEcsResourceDetectorTest(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_not_on_ecs(self):
        actual = AwsEcsResourceDetector().detect()
        self.assertDictEqual(actual.attributes.copy(), {})

    @patch.dict(
        "os.environ",
        {"ECS_CONTAINER_METADATA_URI": "mock-uri"},
        clear=True,
    )
    @patch(
        "socket.gethostname",
        return_value=f"{MockEcsResourceAttributes[ResourceAttributes.CONTAINER_NAME]}",
    )
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"""14:name=systemd:/docker/{MockEcsResourceAttributes[ResourceAttributes.CONTAINER_ID]}
13:rdma:/
12:pids:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
11:hugetlb:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
10:net_prio:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
9:perf_event:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
8:net_cls:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
7:freezer:/docker/
6:devices:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
5:memory:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
4:blkio:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
3:cpuacct:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
2:cpu:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
1:cpuset:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
""",
    )
    def test_simple_create_metadata_v3(
        self,
        mock_open_function,
        mock_socket_gethostname,
    ):
        actual = AwsEcsResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(), OrderedDict(MockEcsResourceAttributes)
        )

    @patch.dict(
        "os.environ",
        {"ECS_CONTAINER_METADATA_URI_V4": MetadataV4Uri},
        clear=True,
    )
    @patch(
        "socket.gethostname",
        return_value=f"{MockEcsResourceAttributes[ResourceAttributes.CONTAINER_NAME]}",
    )
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"""14:name=systemd:/docker/{MockEcsResourceAttributes[ResourceAttributes.CONTAINER_ID]}
13:rdma:/
12:pids:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
11:hugetlb:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
10:net_prio:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
9:perf_event:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
8:net_cls:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
7:freezer:/docker/
6:devices:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
5:memory:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
4:blkio:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
3:cpuacct:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
2:cpu:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
1:cpuset:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
""",
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.ecs._http_get",
    )
    def test_simple_create_metadata_v4_launchtype_ec2(
        self,
        mock_http_get_function,
        mock_open_function,
        mock_socket_gethostname,
    ):
        mock_http_get_function.side_effect = _http_get_function_ec2
        actual = AwsEcsResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(),
            OrderedDict(
                {
                    **MockEcsResourceAttributes,
                    ResourceAttributes.CLOUD_ACCOUNT_ID: "111122223333",
                    ResourceAttributes.CLOUD_AVAILABILITY_ZONE: "us-west-2d",
                    ResourceAttributes.CLOUD_REGION: "us-west-2",
                    ResourceAttributes.CLOUD_RESOURCE_ID: "arn:aws:ecs:us-west-2:111122223333:container/0206b271-b33f-47ab-86c6-a0ba208a70a9",
                    ResourceAttributes.AWS_ECS_CONTAINER_ARN: "arn:aws:ecs:us-west-2:111122223333:container/0206b271-b33f-47ab-86c6-a0ba208a70a9",
                    ResourceAttributes.AWS_ECS_CLUSTER_ARN: "arn:aws:ecs:us-west-2:111122223333:cluster/default",
                    ResourceAttributes.AWS_ECS_LAUNCHTYPE: "ec2",
                    ResourceAttributes.AWS_ECS_TASK_ARN: "arn:aws:ecs:us-west-2:111122223333:task/default/158d1c8083dd49d6b527399fd6414f5c",
                    ResourceAttributes.AWS_ECS_TASK_FAMILY: "curltest",
                    ResourceAttributes.AWS_ECS_TASK_REVISION: "26",
                    ResourceAttributes.AWS_LOG_GROUP_NAMES: ("/ecs/metadata",),
                    ResourceAttributes.AWS_LOG_GROUP_ARNS: (
                        "arn:aws:logs:us-west-2:111122223333:log-group:/ecs/metadata",
                    ),
                    ResourceAttributes.AWS_LOG_STREAM_NAMES: (
                        "ecs/curl/8f03e41243824aea923aca126495f665",
                    ),
                    ResourceAttributes.AWS_LOG_STREAM_ARNS: (
                        "arn:aws:logs:us-west-2:111122223333:log-group:/ecs/metadata:log-stream:ecs/curl/8f03e41243824aea923aca126495f665",
                    ),
                }
            ),
        )

    @patch.dict(
        "os.environ",
        {"ECS_CONTAINER_METADATA_URI_V4": MetadataV4Uri},
        clear=True,
    )
    @patch(
        "socket.gethostname",
        return_value=f"{MockEcsResourceAttributes[ResourceAttributes.CONTAINER_NAME]}",
    )
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"""14:name=systemd:/docker/{MockEcsResourceAttributes[ResourceAttributes.CONTAINER_ID]}
13:rdma:/
12:pids:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
11:hugetlb:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
10:net_prio:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
9:perf_event:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
8:net_cls:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
7:freezer:/docker/
6:devices:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
5:memory:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
4:blkio:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
3:cpuacct:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
2:cpu:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
1:cpuset:/docker/bogusContainerIdThatShouldNotBeOneSetBecauseTheFirstOneWasPicked
""",
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.ecs._http_get",
    )
    def test_simple_create_metadata_v4_launchtype_fargate(
        self,
        mock_http_get_function,
        mock_open_function,
        mock_socket_gethostname,
    ):
        mock_http_get_function.side_effect = _http_get_function_fargate
        actual = AwsEcsResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(),
            OrderedDict(
                {
                    **MockEcsResourceAttributes,
                    ResourceAttributes.CLOUD_ACCOUNT_ID: "111122223333",
                    ResourceAttributes.CLOUD_AVAILABILITY_ZONE: "us-west-2a",
                    ResourceAttributes.CLOUD_REGION: "us-west-2",
                    ResourceAttributes.CLOUD_RESOURCE_ID: "arn:aws:ecs:us-west-2:111122223333:container/05966557-f16c-49cb-9352-24b3a0dcd0e1",
                    ResourceAttributes.AWS_ECS_CONTAINER_ARN: "arn:aws:ecs:us-west-2:111122223333:container/05966557-f16c-49cb-9352-24b3a0dcd0e1",
                    ResourceAttributes.AWS_ECS_CLUSTER_ARN: "arn:aws:ecs:us-west-2:111122223333:cluster/default",
                    ResourceAttributes.AWS_ECS_LAUNCHTYPE: "fargate",
                    ResourceAttributes.AWS_ECS_TASK_ARN: "arn:aws:ecs:us-west-2:111122223333:task/default/e9028f8d5d8e4f258373e7b93ce9a3c3",
                    ResourceAttributes.AWS_ECS_TASK_FAMILY: "curltest",
                    ResourceAttributes.AWS_ECS_TASK_REVISION: "3",
                    ResourceAttributes.AWS_LOG_GROUP_NAMES: (
                        "/ecs/containerlogs",
                    ),
                    ResourceAttributes.AWS_LOG_GROUP_ARNS: (
                        "arn:aws:logs:us-west-2:111122223333:log-group:/ecs/containerlogs",
                    ),
                    ResourceAttributes.AWS_LOG_STREAM_NAMES: (
                        "ecs/curl/cd189a933e5849daa93386466019ab50",
                    ),
                    ResourceAttributes.AWS_LOG_STREAM_ARNS: (
                        "arn:aws:logs:us-west-2:111122223333:log-group:/ecs/containerlogs:log-stream:ecs/curl/cd189a933e5849daa93386466019ab50",
                    ),
                }
            ),
        )
