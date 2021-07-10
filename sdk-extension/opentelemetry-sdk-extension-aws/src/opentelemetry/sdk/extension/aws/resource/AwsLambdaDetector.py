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


class AwsLambdaResourceDetector(ResourceDetector):
    def detect(self) -> "Resource":
        try:
            # NOTE: (NathanielRN) Should ResourceDetectors use Resource.detect() to pull in the environment variable?
            # `OTELResourceDetector` doesn't do this...
            return Resource(
                {
                    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS,
                    ResourceAttributes.CLOUD_PLATFORM: CloudInfrastructureServiceValues.AWS_LAMBDA,
                    ResourceAttributes.CLOUD_REGION: environ.get("AWS_REGION"),
                    ResourceAttributes.FAAS_NAME: environ.get(
                        "AWS_LAMBDA_FUNCTION_NAME"
                    ),
                    ResourceAttributes.FAAS_VERSION: environ.get(
                        "AWS_LAMBDA_FUNCTION_VERSION"
                    ),
                }
            )
        except Exception as e:
            logger.debug(f"AwsLambdaDetector failed: {e}")
            return Resource.get_empty()
