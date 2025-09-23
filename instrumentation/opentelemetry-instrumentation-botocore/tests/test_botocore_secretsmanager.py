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

import botocore.session
from moto import mock_aws

from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.semconv._incubating.attributes.aws_attributes import (
    AWS_SECRETSMANAGER_SECRET_ARN,
)
from opentelemetry.test.test_base import TestBase


class TestSecretsManagerExtension(TestBase):
    def setUp(self):
        super().setUp()
        BotocoreInstrumentor().instrument()
        session = botocore.session.get_session()
        session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.region = "us-west-2"
        self.client = session.create_client(
            "secretsmanager", region_name=self.region
        )

    def tearDown(self):
        super().tearDown()
        BotocoreInstrumentor().uninstrument()

    def create_secret_and_get_arn(self, name: str = "test-secret") -> str:
        """
        Create a secret in mocked Secrets Manager and return its ARN.
        """
        # Clear spans before creating secret for helper method
        self.memory_exporter.clear()
        response = self.client.create_secret(
            Name=name, SecretString="test-secret-value"
        )
        return response["ARN"]

    @mock_aws
    def test_tag_resource_with_arn(self):
        secret_arn = self.create_secret_and_get_arn()

        self.client.tag_resource(
            SecretId=secret_arn, Tags=[{"Key": "Environment", "Value": "Test"}]
        )

        spans = self.memory_exporter.get_finished_spans()
        assert spans
        self.assertEqual(len(spans), 2)
        span = spans[1]  # tag_resource span
        self.assertEqual(
            span.attributes[AWS_SECRETSMANAGER_SECRET_ARN],
            secret_arn,
        )

    @mock_aws
    def test_create_secret(self):
        secret_name = "test-secret"
        response = self.client.create_secret(
            Name=secret_name, SecretString="test-secret-value"
        )
        secret_arn = response["ARN"]

        spans = self.memory_exporter.get_finished_spans()
        assert spans
        self.assertEqual(len(spans), 1)
        span = spans[0]  # create_secret span
        # Should capture ARN from response
        self.assertEqual(
            span.attributes[AWS_SECRETSMANAGER_SECRET_ARN],
            secret_arn,
        )
