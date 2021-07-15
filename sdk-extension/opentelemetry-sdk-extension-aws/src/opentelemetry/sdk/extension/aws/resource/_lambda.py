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
from os import environ

from opentelemetry.sdk.resources import Resource, ResourceDetector
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)

logger = logging.getLogger(__name__)


class AwsLambdaResourceDetector(ResourceDetector):
    """Detects attribute values only available when the app is running on AWS
    Lambda and returns them in a Resource.
    """

    def __init__(self, raise_on_error=False):
        super().__init__(raise_on_error=raise_on_error)

    def detect(self) -> "Resource":
        try:
            # NOTE: (NathanielRN) Should ResourceDetectors use Resource.create() to pull in the environment variable?
            # `OTELResourceDetector` doesn't do this...
            return Resource(
                {
                    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS.value,
                    ResourceAttributes.CLOUD_PLATFORM: CloudPlatformValues.AWS_LAMBDA.value,
                    ResourceAttributes.CLOUD_REGION: environ["AWS_REGION"],
                    ResourceAttributes.FAAS_NAME: environ[
                        "AWS_LAMBDA_FUNCTION_NAME"
                    ],
                    ResourceAttributes.FAAS_VERSION: environ[
                        "AWS_LAMBDA_FUNCTION_VERSION"
                    ],
                    ResourceAttributes.FAAS_INSTANCE: environ[
                        "AWS_LAMBDA_LOG_STREAM_NAME"
                    ],
                    ResourceAttributes.FAAS_MAX_MEMORY: int(
                        environ["AWS_LAMBDA_FUNCTION_MEMORY_SIZE"]
                    ),
                }
            )
        except Exception as e:
            logger.debug(f"{self.__class__.__name__} failed: {e}")
            return Resource.get_empty()
