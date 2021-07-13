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
import ssl
from urllib.request import Request, urlopen
from opentelemetry.sdk.resources import (
    Resource,
    ResourceDetector,
)
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)

logger = logging.getLogger(__name__)

_CONTAINER_ID_LENGTH = 64
_GET_METHOD = "GET"


def _aws_http_request(method, path, cred_value, cert):
    response = urlopen(
        Request(
            "http://kubernetes.default.svc" + path, headers={"Authorization": cred_value}, method=method
        ),
        timeout=2000,
        context=ssl.create_default_context(cafile=cert)
    )
    return response.read().decode('utf-8')


def _get_k8s_cred_value():
    try:
        with open(
            "/var/run/secrets/kubernetes.io/serviceaccount/token",
            encoding="utf8",
        ) as f:
            return "Bearer" + f.read()
    except:
        return ""


def _is_Eks(cert, cred_value):
    return _aws_http_request(
        _GET_METHOD,
        "/api/v1/namespaces/kube-system/configmaps/aws-auth",
        cred_value,
        cert,
    )


def _get_cluster_info(cert, cred_value):
    return _aws_http_request(
        _GET_METHOD,
        "/api/v1/namespaces/amazon-cloudwatch/configmaps/cluster-info",
        cred_value,
        cert,
    )


class AwsEksResourceDetector(ResourceDetector):
    def detect(self) -> "Resource":
        try:

            cred_value = _get_k8s_cred_value()
            with open(
                "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
            ) as f:
                k8_cert = f.read()
                if not _is_Eks(k8_cert, cred_value):
                    return Resource.get_empty()

            with open("proc/self/cgroup", encoding="utf8") as f:
                for line in f.readlines():
                    if len(line) > _CONTAINER_ID_LENGTH:
                        container_id = line[-_CONTAINER_ID_LENGTH:]

            cluster_info = json.load(_get_cluster_info())

            if not container_id or not cluster_info:
                return Resource.get_empty()

            # NOTE: (NathanielRN) Should ResourceDetectors use Resource.create() to pull in the environment variable?
            # `OTELResourceDetector` doesn't do this...
            return Resource(
                {
                    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS.value,
                    ResourceAttributes.CLOUD_PLATFORM: CloudPlatformValues.AWS_EKS.value,
                    ResourceAttributes.K8S_CLUSTER_NAME: cluster_info["data"][
                        "cluster.name"
                    ],
                    ResourceAttributes.CONTAINER_ID: container_id,
                }
            )
        except Exception as e:
            logger.debug(f"{self.__class__.__name__} failed: {e}")
            return Resource.get_empty()
