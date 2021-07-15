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

from collections import OrderedDict
import unittest
from unittest.mock import patch, mock_open

from opentelemetry.sdk.extension.aws.resource.ecs import (
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


class AwsEcsResourceDetectorTest(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "ECS_CONTAINER_METADATA_URI": "mock-uri",
        },
        clear=True,
    )
    @patch(
        "socket.gethostname",
        return_value=f"{MockEcsResourceAttributes[ResourceAttributes.CONTAINER_NAME]}",
    )
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"""12:perf_event:/
11:cpuset:/
10:devices:/
9:freezer:/
8:cpu,cpuacct:/
7:blkio:/
6:pids:/
5:hugetlb:/
4:net_cls,net_prio:/
3:memory:/
2:cpu:/docker/{MockEcsResourceAttributes[ResourceAttributes.CONTAINER_ID]}
1:name=systemd:/user.slice/user-1000.slice/session-34.scope
""",
    )
    def test_simple_create(self, mock_open_function, mock_socket_gethostname):
        actual = AwsEcsResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(), OrderedDict(MockEcsResourceAttributes)
        )
