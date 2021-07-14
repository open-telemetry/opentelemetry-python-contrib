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

_AWS_METADATA_TOKEN_HEADER = "X-aws-ec2-metadata-token"
_GET_METHOD = "GET"


def _aws_http_request(method, path, headers):
    response = urlopen(
        Request(
            "http://169.254.169.254" + path, headers=headers, method=method
        ),
        timeout=1000,
    )
    return response.read().decode('utf-8')


def _get_token():
    return _aws_http_request(
        "PUT",
        "/latest/api/token",
        {"X-aws-ec2-metadata-token-ttl-seconds": "60"},
    )


def _get_identity(token):
    return _aws_http_request(
        _GET_METHOD,
        "/latest/dynamic/instance-identity/document",
        {_AWS_METADATA_TOKEN_HEADER: token},
    )


def _get_host(token):
    return _aws_http_request(
        _GET_METHOD,
        "/latest/meta-data/hostname",
        {_AWS_METADATA_TOKEN_HEADER: token},
    )


class AwsEc2ResourceDetector(ResourceDetector):
    """Detects attribute values only available when the app is running on AWS
    Elastic Compute Cloud (EC2) and returns them in a Resource.
    """
    def detect(self) -> "Resource":
        # raise Exception("GOT EM")
        try:
            token = _get_token()
            identity_dict = json.loads(_get_identity(token))
            hostname = _get_host(token)

            # NOTE: (NathanielRN) Should ResourceDetectors use Resource.create() to pull in the environment variable?
            # `OTELResourceDetector` doesn't do this...
            return Resource(
                {
                    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS.value,
                    ResourceAttributes.CLOUD_PLATFORM: CloudPlatformValues.AWS_EC2.value,
                    ResourceAttributes.CLOUD_ACCOUNT_ID: identity_dict[
                        "accountId"
                    ],
                    ResourceAttributes.CLOUD_REGION: identity_dict["region"],
                    ResourceAttributes.CLOUD_AVAILABILITY_ZONE: identity_dict[
                        "availabilityZone"
                    ],
                    ResourceAttributes.HOST_ID: identity_dict["instanceId"],
                    ResourceAttributes.HOST_TYPE: identity_dict["instanceType"],
                    ResourceAttributes.HOST_NAME: hostname,
                }
            )
        except Exception as e:
            logger.debug(f"{self.__class__.__name__} failed: {e}")
            return Resource.get_empty()
