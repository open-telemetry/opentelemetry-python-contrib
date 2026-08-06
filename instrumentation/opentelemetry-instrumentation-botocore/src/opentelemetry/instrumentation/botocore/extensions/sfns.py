# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from opentelemetry.instrumentation.botocore.extensions.types import (
    _AttributeMapT,
    _AwsSdkExtension,
    _BotocoreInstrumentorContext,
    _BotoResultT,
)
from opentelemetry.semconv._incubating.attributes.aws_attributes import (
    AWS_STEP_FUNCTIONS_ACTIVITY_ARN,
    AWS_STEP_FUNCTIONS_STATE_MACHINE_ARN,
)
from opentelemetry.trace.span import Span


class _StepFunctionsExtension(_AwsSdkExtension):
    @staticmethod
    def _set_arn_attributes(source, target, setter_func):
        """Helper to set ARN attributes if they exist in source."""
        activity_arn = source.get("activityArn")
        if activity_arn:
            setter_func(target, AWS_STEP_FUNCTIONS_ACTIVITY_ARN, activity_arn)

        state_machine_arn = source.get("stateMachineArn")
        if state_machine_arn:
            setter_func(
                target, AWS_STEP_FUNCTIONS_STATE_MACHINE_ARN, state_machine_arn
            )

    def extract_attributes(self, attributes: _AttributeMapT):
        self._set_arn_attributes(
            self._call_context.params,
            attributes,
            lambda target, key, value: target.__setitem__(key, value),
        )

    def on_success(
        self,
        span: Span,
        result: _BotoResultT,
        instrumentor_context: _BotocoreInstrumentorContext,
    ):
        self._set_arn_attributes(
            result,
            span,
            lambda target, key, value: target.set_attribute(key, value),
        )
