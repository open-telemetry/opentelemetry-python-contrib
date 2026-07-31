# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

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

    Uses Lambda defined runtime environment variables. See more: https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html#configuration-envvars-runtime
    """

    def detect(self) -> "Resource":
        try:
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
        # pylint: disable=broad-except
        except Exception as exception:
            if self.raise_on_error:
                raise exception

            logger.warning("%s failed: %s", self.__class__.__name__, exception)
            return Resource.get_empty()
