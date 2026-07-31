# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import unittest
from collections import OrderedDict
from unittest.mock import patch

from opentelemetry.sdk.extension.aws.resource._lambda import (  # pylint: disable=no-name-in-module
    AwsLambdaResourceDetector,
)
from opentelemetry.semconv.resource import (
    CloudPlatformValues,
    CloudProviderValues,
    ResourceAttributes,
)

MockLambdaResourceAttributes = {
    ResourceAttributes.CLOUD_PROVIDER: CloudProviderValues.AWS.value,
    ResourceAttributes.CLOUD_PLATFORM: CloudPlatformValues.AWS_LAMBDA.value,
    ResourceAttributes.CLOUD_REGION: "mock-west-2",
    ResourceAttributes.FAAS_NAME: "mock-lambda-name",
    ResourceAttributes.FAAS_VERSION: "mock-version-42",
    ResourceAttributes.FAAS_INSTANCE: "mock-log-stream",
    ResourceAttributes.FAAS_MAX_MEMORY: 128,
}


class AwsLambdaResourceDetectorTest(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "AWS_REGION": MockLambdaResourceAttributes[
                ResourceAttributes.CLOUD_REGION
            ],
            "AWS_LAMBDA_FUNCTION_NAME": MockLambdaResourceAttributes[
                ResourceAttributes.FAAS_NAME
            ],
            "AWS_LAMBDA_FUNCTION_VERSION": MockLambdaResourceAttributes[
                ResourceAttributes.FAAS_VERSION
            ],
            "AWS_LAMBDA_LOG_STREAM_NAME": MockLambdaResourceAttributes[
                ResourceAttributes.FAAS_INSTANCE
            ],
            "AWS_LAMBDA_FUNCTION_MEMORY_SIZE": f"{MockLambdaResourceAttributes[ResourceAttributes.FAAS_MAX_MEMORY]}",
        },
        clear=True,
    )
    def test_simple_create(self):
        actual = AwsLambdaResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(), OrderedDict(MockLambdaResourceAttributes)
        )
