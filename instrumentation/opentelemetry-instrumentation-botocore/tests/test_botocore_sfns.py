import json

import botocore.session
from moto import mock_aws

from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.semconv._incubating.attributes.aws_attributes import (
    AWS_STEP_FUNCTIONS_ACTIVITY_ARN,
    AWS_STEP_FUNCTIONS_STATE_MACHINE_ARN,
)
from opentelemetry.test.test_base import TestBase


class TestSfnsExtension(TestBase):
    def setUp(self):
        super().setUp()
        BotocoreInstrumentor().instrument()
        session = botocore.session.get_session()
        session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.region = "us-west-2"
        self.client = session.create_client(
            "stepfunctions", region_name=self.region
        )

    def tearDown(self):
        super().tearDown()
        BotocoreInstrumentor().uninstrument()

    SIMPLE_STATE_MACHINE_DEF = {
        "Comment": "A simple Hello World example",
        "StartAt": "HelloState",
        "States": {
            "HelloState": {
                "Type": "Pass",
                "Result": "Hello, Moto!",
                "End": True,
            }
        },
    }

    def create_state_machine_and_get_arn(
        self, name: str = "TestStateMachine"
    ) -> str:
        """
        Create a state machine in mocked Step Functions and return its ARN.
        """
        definition_json = json.dumps(self.SIMPLE_STATE_MACHINE_DEF)
        role_arn = "arn:aws:iam::123456789012:role/DummyRole"

        response = self.client.create_state_machine(
            name=name,
            definition=definition_json,
            roleArn=role_arn,
        )
        return response["stateMachineArn"]

    def create_activity_and_get_arn(self, name: str = "TestActivity") -> str:
        """
        Create an activity in mocked Step Functions and return its ARN.
        """
        response = self.client.create_activity(
            name=name,
        )
        return response["activityArn"]

    @mock_aws
    def test_sfns_create_state_machine(self):
        state_machine_arn = self.create_state_machine_and_get_arn()
        spans = self.memory_exporter.get_finished_spans()
        assert spans
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(
            span.attributes[AWS_STEP_FUNCTIONS_STATE_MACHINE_ARN],
            state_machine_arn,
        )

    @mock_aws
    def test_sfns_describe_state_machine(self):
        state_machine_arn = self.create_state_machine_and_get_arn()
        self.client.describe_state_machine(stateMachineArn=state_machine_arn)

        spans = self.memory_exporter.get_finished_spans()
        assert spans
        self.assertEqual(len(spans), 2)
        span = spans[1]
        self.assertEqual(
            span.attributes[AWS_STEP_FUNCTIONS_STATE_MACHINE_ARN],
            state_machine_arn,
        )

    @mock_aws
    def test_sfns_create_activity(self):
        activity_arn = self.create_activity_and_get_arn()
        spans = self.memory_exporter.get_finished_spans()
        assert spans
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(
            span.attributes[AWS_STEP_FUNCTIONS_ACTIVITY_ARN],
            activity_arn,
        )

    @mock_aws
    def test_sfns_describe_activity(self):
        activity_arn = self.create_activity_and_get_arn()
        self.client.describe_activity(activityArn=activity_arn)
        spans = self.memory_exporter.get_finished_spans()
        assert spans
        self.assertEqual(len(spans), 2)
        span = spans[1]
        self.assertEqual(
            span.attributes[AWS_STEP_FUNCTIONS_ACTIVITY_ARN],
            activity_arn,
        )
