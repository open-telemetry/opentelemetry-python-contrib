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
from unittest.mock import MagicMock, patch, mock_open

from opentelemetry.sdk.extension.aws.resource.eks import AwsEksResourceDetector
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)

MockEksResourceAttributes = {
    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS.value,
    ResourceAttributes.CLOUD_PLATFORM: CloudPlatformValues.AWS_EKS.value,
    ResourceAttributes.K8S_CLUSTER_NAME: "mock-cluster-name",
    ResourceAttributes.CONTAINER_ID: "a4d00c9dd675d67f866c786181419e1b44832d4696780152e61afd44a3e02856",
}

files_for_stack_of_mock_open_calls = [
    f"""12:perf_event:/
11:cpuset:/
10:devices:/
9:freezer:/
8:cpu,cpuacct:/
7:blkio:/
6:pids:/
5:hugetlb:/
4:net_cls,net_prio:/
3:memory:/
2:cpu:/docker/{MockEksResourceAttributes[ResourceAttributes.CONTAINER_ID]}
1:name=systemd:/user.slice/user-1000.slice/session-34.scope
""",
    """-----BEGIN CERTIFICATE-----
MOCKCeRTIf1ICATe+ERthElKtzANBgkqhkiG9w0BAQsFADBdMQswCQYDVQQGEwJB
MOCKCeRTIf1ICATeQXVzdHJhbGlhMQ8wDQYDVQQHDAZTeWRuZXkxEjAQBgNVBAoM
MOCKCeRTIf1ICATeMBMGA1UEAwwMTXlDb21tb25OYW1lMB4XDTIwMDkyMjA1MjIx
MOCKCeRTIf1ICATeMjIxMFowXTELMAkGA1UEBhMCQVUxEjAQBgNVBAgMCUF1c3Ry
MOCKCeRTIf1ICATeBwwGU3lkbmV5MRIwEAYDVQQKDAlNeU9yZ05hbWUxFTATBgNV
MOCKCeRTIf1ICATeTmFtZTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEB
MOCKCeRTIf1ICATeWq9mZzqLREoLTfNG8pRCPFvD+UEbl7ldLrzz5T92s4VX7HjA
MOCKCeRTIf1ICATeXV1fBlbFcAmkISiYWYCmIxD1BfEN+Sh/9OVfKXZJVSInvs/I
MOCKCeRTIf1ICATe/hlcZW9VA2IUkbTUb/qd7SK0pVpOK0KMdpVq5t1HqAP+ssB/
MOCKCeRTIf1ICATei+s7LfMeiPya9hY/CRk6ei3oSrxLqQCXUeJAtS/iMzUDyq7u
MOCKCeRTIf1ICATeF9AkUXRqp8DVsIJKGk4hN/aKvkJaJfHe66kirKeJWQXYp5Hh
MOCKCeRTIf1ICATew50YnbsCAwEAATANBgkqhkiG9w0BAQsFAAOCAQEAwEEc13Oi
MOCKCeRTIf1ICATeuNn9qTdXBjNwgQV9z0QZrw9puGAAc1oRs8cmPx+TMROSPzXM
MOCKCeRTIf1ICATej4iRVm0rYm796q8IaicerkpN5XzFSeyzwnwMauyOA9cXsMfB
MOCKCeRTIf1ICATeTuBD03Ic0kfz39bz0gPod6/CWo7ONRV6AoEwVi1vsULLUbA0
MOCKCeRTIf1ICATex1DB5lKrATyFPCxR+kq6Q+EdfDq3r+B7rg+gyv6mCzaf5LZY
MOCKCeRTIf1ICATeRebvp00i0RfeqSu3Uwr51oEidkLeBQftQm9Xvkt4Z3O+LJjw
bf40dGXtFmgflw==
-----END CERTIFICATE-----
""",
]


class AwsEksResourceDetectorTest(unittest.TestCase):
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_cluster_info",
        return_value=f"""{{
  "data": {{
    "cluster.name": "{MockEksResourceAttributes[ResourceAttributes.K8S_CLUSTER_NAME]}",
    "force_flush_interval": 5
  }}
}}
""",
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_Eks",
        return_value=True,
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_k8s_cred_value",
        return_value="MOCK_TOKEN",
    )
    @patch(
        "builtins.open",
        new_callable=lambda: mock_open(
            read_data=files_for_stack_of_mock_open_calls.pop(0)
        ),
    )
    def test_simple_create(
        self,
        mock_open_function,
        mock_get_k8_cred_value,
        mock_is_Eks,
        mock_get_cluster_info,
    ):
        actual = AwsEksResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(), OrderedDict(MockEksResourceAttributes)
        )
