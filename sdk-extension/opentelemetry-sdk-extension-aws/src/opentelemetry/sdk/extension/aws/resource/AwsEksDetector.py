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
import requests
from opentelemetry.sdk.resources import (
    Resource,
    ResourceDetector,
)
from opentelemetry.semconv.resource import (
    CloudInfrastructureServiceValues,
    CloudProviderValues,
    ResourceAttributes,
)

logger = logging.getLogger(__name__)

_CONTAINER_ID_LENGTH = 64
_GET_METHOD = "GET"


def _aws_http_request(method, path, cred_header, cert):
    response = requests.request(
        method=method,
        url="kubernetes.default.svc" + path,
        headers=[{"Authorization": cred_header}],
        timeout=2000,
        cert=cert,
    )
    return response


def _get_k8s_cred_header():
    try:
        with open(
            "/var/run/secrets/kubernetes.io/serviceaccount/token",
            encoding="utf8",
        ) as f:
            return "Bearer" + f.read()
    except:
        return ""


def _is_Eks(cert, cred_header):
    return _aws_http_request(
        _GET_METHOD,
        "/api/v1/namespaces/kube-system/configmaps/aws-auth",
        cred_header,
        cert,
    )


def _get_cluster_info(cert, cred_header):
    return _aws_http_request(
        _GET_METHOD,
        "/api/v1/namespaces/amazon-cloudwatch/configmaps/cluster-info",
        cred_header,
        cert,
    )


class AwsEksDetector(ResourceDetector):
    def detect(self) -> "Resource":
        try:

            cred_header = _get_k8s_cred_header()
            with open(
                "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
            ) as f:
                k8_cert = f.read()
                if not _is_Eks(k8_cert, cred_header):
                    return Resource.get_empty()

            with open("proc/self/cgroup", encoding="utf8") as f:
                for line in f.readlines():
                    if len(line) > _CONTAINER_ID_LENGTH:
                        container_id = line[-_CONTAINER_ID_LENGTH:]

            cluster_info = json.load(_get_cluster_info())

            if not container_id or not cluster_info:
                return Resource.get_empty()

            # NOTE: (NathanielRN) Should ResourceDetectors use Resource.detect() to pull in the environment variable?
            # `OTELResourceDetector` doesn't do this...
            return Resource(
                {
                    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS,
                    ResourceAttributes.CLOUD_PLATFORM: CloudInfrastructureServiceValues.AWS_EKS,
                    ResourceAttributes.K8S_CLUSTER_NAME: cluster_info["data"][
                        "cluter.name"
                    ],
                    ResourceAttributes.CONTAINER_ID: container_id,
                }
            )
        except Exception as e:
            logger.debug(f"AwsEcsDetector failed: {e}")
            return Resource.get_empty()
