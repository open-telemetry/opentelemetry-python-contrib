# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import unittest
from collections import OrderedDict
from unittest.mock import mock_open, patch

from opentelemetry.sdk.extension.aws.resource.eks import (  # pylint: disable=no-name-in-module
    AwsEksResourceDetector,
)
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)


def _bearer_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"Bearer {header}.{body}.fakesig"


MockEksResourceAttributes = {
    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS.value,
    ResourceAttributes.CLOUD_PLATFORM: CloudPlatformValues.AWS_EKS.value,
    ResourceAttributes.K8S_CLUSTER_NAME: "mock-cluster-name",
    ResourceAttributes.CONTAINER_ID: "a4d00c9dd675d67f866c786181419e1b44832d4696780152e61afd44a3e02856",
}


class AwsEksResourceDetectorTest(unittest.TestCase):
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_k8s_cred_value",
        return_value="MOCK_TOKEN",
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_eks",
        return_value=True,
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_k8s",
        return_value=True,
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_cluster_info",
        return_value=(
            "{\n"
            '  "kind": "ConfigMap",\n'
            '  "apiVersion": "v1",\n'
            '  "metadata": {\n'
            '    "name": "cluster-info",\n'
            '    "namespace": "amazon-cloudwatch",\n'
            '    "selfLink": "/api/v1/namespaces/amazon-cloudwatch/configmaps/cluster-info",\n'
            '    "uid": "0734438c-48f4-45c3-b06d-b6f16f7f0e1e",\n'
            '    "resourceVersion": "25911",\n'
            '    "creationTimestamp": "2021-07-23T18:41:56Z",\n'
            '    "annotations": {\n'
            '      "kubectl.kubernetes.io/last-applied-configuration": '
            '"{\\"apiVersion\\":\\"v1\\",\\"data\\":{\\"cluster.name\\":\\"'
            f"{MockEksResourceAttributes[ResourceAttributes.K8S_CLUSTER_NAME]}"
            '\\",\\"logs.region\\":\\"us-west-2\\"},\\"kind\\":\\"ConfigMap\\",'
            '\\"metadata\\":{\\"annotations\\":{},\\"name\\":\\"cluster-info\\",'
            '\\"namespace\\":\\"amazon-cloudwatch\\"}}\\n"\n'
            "    }\n"
            "  },\n"
            '  "data": {\n'
            f'    "cluster.name": "{MockEksResourceAttributes[ResourceAttributes.K8S_CLUSTER_NAME]}",\n'
            '    "logs.region": "us-west-2"\n'
            "  }\n"
            "}\n"
        ),
    )
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"""14:name=systemd:/docker/{MockEksResourceAttributes[ResourceAttributes.CONTAINER_ID]}
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
    def test_simple_create(
        self,
        mock_open_function,
        mock_get_cluster_info,
        mock_is_k8s,
        mock_is_eks,
        mock_get_k8_cred_value,
    ):
        actual = AwsEksResourceDetector().detect()
        self.assertDictEqual(actual.attributes.copy(), OrderedDict(MockEksResourceAttributes))

    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_k8s_cred_value",
        return_value="MOCK_TOKEN",
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_eks",
        return_value=False,
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_k8s",
        return_value=True,
    )
    def test_if_no_eks_env_var_and_should_raise(self, mock_is_k8s, mock_is_eks, mock_get_k8_cred_value):
        with self.assertRaises(RuntimeError):
            AwsEksResourceDetector(raise_on_error=True).detect()

    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_k8s_cred_value",
        return_value="MOCK_TOKEN",
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_eks",
        return_value=False,
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_k8s",
        return_value=False,
    )
    def test_if_no_eks_paths_should_not_raise(self, mock_is_k8s, mock_is_eks, mock_get_k8_cred_value):
        try:
            AwsEksResourceDetector(raise_on_error=True).detect()
        except RuntimeError:
            self.fail("Should not raise")

    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_k8s_cred_value",
        return_value=_bearer_jwt(
            {"iss": "https://oidc.eks.eu-west-2.amazonaws.com/id/A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"}
        ),
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_k8s",
        return_value=True,
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_cluster_info",
        return_value=f"""{{
  "data": {{
    "cluster.name": "{MockEksResourceAttributes[ResourceAttributes.K8S_CLUSTER_NAME]}"
  }}
}}
""",
    )
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=f"14:name=systemd:/docker/{MockEksResourceAttributes[ResourceAttributes.CONTAINER_ID]}\n",
    )
    def test_eks_oidc_jwt_detected(
        self,
        mock_open_function,
        mock_get_cluster_info,
        mock_is_k8s,
        mock_get_k8s_cred_value,
    ):
        actual = AwsEksResourceDetector().detect()
        self.assertEqual(
            actual.attributes.get(ResourceAttributes.CLOUD_PLATFORM),
            CloudPlatformValues.AWS_EKS.value,
        )

    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_k8s_cred_value",
        return_value=_bearer_jwt({"iss": "https://accounts.google.com"}),
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_k8s",
        return_value=True,
    )
    def test_non_eks_jwt_returns_empty(self, mock_is_k8s, mock_get_k8s_cred_value):
        actual = AwsEksResourceDetector().detect()
        self.assertEqual(actual.attributes, {})

    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_k8s_cred_value",
        return_value=_bearer_jwt({"iss": "https://wrong.jwt.com"}),
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_k8s",
        return_value=True,
    )
    def test_non_eks_jwt_should_raise(self, mock_is_k8s, mock_get_k8s_cred_value):
        with self.assertRaises(RuntimeError):
            AwsEksResourceDetector(raise_on_error=True).detect()

    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_k8s_cred_value",
        return_value="Bearer notajwt.otel",
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_k8s",
        return_value=True,
    )
    def test_is_eks_wrong_parts_count_should_raise(self, mock_is_k8s, mock_get_k8s_cred_value):
        with self.assertRaises(RuntimeError):
            AwsEksResourceDetector(raise_on_error=True).detect()

    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._get_k8s_cred_value",
        return_value="Bearer header.eyJpc3MiOg.fakesig",
    )
    @patch(
        "opentelemetry.sdk.extension.aws.resource.eks._is_k8s",
        return_value=True,
    )
    def test_is_eks_invalid_json_payload_should_raise(self, mock_is_k8s, mock_get_k8s_cred_value):
        with self.assertRaises(RuntimeError):
            AwsEksResourceDetector(raise_on_error=True).detect()
