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

import os
import unittest
from collections import OrderedDict
from unittest.mock import patch

import pytest

from opentelemetry.sdk.extension.aws.resource._lambda import (  # pylint: disable=no-name-in-module
    AwsLambdaResourceDetector,
    _ACCOUNT_ID_SYMLINK_PATH,
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

MOCK_LAMBDA_ENV = {
    "AWS_REGION": MockLambdaResourceAttributes[ResourceAttributes.CLOUD_REGION],
    "AWS_LAMBDA_FUNCTION_NAME": MockLambdaResourceAttributes[ResourceAttributes.FAAS_NAME],
    "AWS_LAMBDA_FUNCTION_VERSION": MockLambdaResourceAttributes[ResourceAttributes.FAAS_VERSION],
    "AWS_LAMBDA_LOG_STREAM_NAME": MockLambdaResourceAttributes[ResourceAttributes.FAAS_INSTANCE],
    "AWS_LAMBDA_FUNCTION_MEMORY_SIZE": f"{MockLambdaResourceAttributes[ResourceAttributes.FAAS_MAX_MEMORY]}",
}


class AwsLambdaResourceDetectorTest(unittest.TestCase):
    @patch.dict(
        "os.environ",
        MOCK_LAMBDA_ENV,
        clear=True,
    )
    def test_simple_create(self):
        actual = AwsLambdaResourceDetector().detect()
        self.assertDictEqual(
            actual.attributes.copy(), OrderedDict(MockLambdaResourceAttributes)
        )


@pytest.fixture
def account_id_symlink(tmp_path):
    """Create a symlink at a temporary path and patch the detector to use it."""
    def _create(account_id):
        symlink_path = tmp_path / ".otel-aws-account-id"
        os.symlink(account_id, symlink_path)
        return str(symlink_path)
    return _create


@patch.dict("os.environ", MOCK_LAMBDA_ENV, clear=True)
def test_account_id_from_symlink(account_id_symlink):
    """When the account ID symlink exists, cloud.account.id is set."""
    symlink_path = account_id_symlink("123456789012")
    with patch(
        "opentelemetry.sdk.extension.aws.resource._lambda._ACCOUNT_ID_SYMLINK_PATH",
        symlink_path,
    ):
        actual = AwsLambdaResourceDetector().detect()
    assert actual.attributes[ResourceAttributes.CLOUD_ACCOUNT_ID] == "123456789012"


@patch.dict("os.environ", MOCK_LAMBDA_ENV, clear=True)
def test_account_id_missing_symlink():
    """When the symlink does not exist, cloud.account.id is absent and no exception is raised."""
    with patch(
        "opentelemetry.sdk.extension.aws.resource._lambda._ACCOUNT_ID_SYMLINK_PATH",
        "/tmp/.otel-aws-account-id-nonexistent",
    ):
        actual = AwsLambdaResourceDetector().detect()
    assert ResourceAttributes.CLOUD_ACCOUNT_ID not in actual.attributes


@patch.dict("os.environ", MOCK_LAMBDA_ENV, clear=True)
def test_account_id_preserves_leading_zeros(account_id_symlink):
    """Leading zeros in the account ID are preserved (treated as string)."""
    symlink_path = account_id_symlink("000123456789")
    with patch(
        "opentelemetry.sdk.extension.aws.resource._lambda._ACCOUNT_ID_SYMLINK_PATH",
        symlink_path,
    ):
        actual = AwsLambdaResourceDetector().detect()
    assert actual.attributes[ResourceAttributes.CLOUD_ACCOUNT_ID] == "000123456789"
