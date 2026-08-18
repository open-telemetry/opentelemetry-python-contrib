# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from opentelemetry.instrumentation.botocore.extensions.types import (
    _AttributeMapT,
    _AwsSdkExtension,
    _BotocoreInstrumentorContext,
    _BotoResultT,
)
from opentelemetry.semconv._incubating.attributes.aws_attributes import (
    AWS_SECRETSMANAGER_SECRET_ARN,
)
from opentelemetry.trace.span import Span


class _SecretsManagerExtension(_AwsSdkExtension):
    def extract_attributes(self, attributes: _AttributeMapT):
        """
        SecretId is extracted if a secret ARN, the function extracts the attribute
        only if the SecretId parameter is provided as an arn which starts with
        `arn:aws:secretsmanager:`
        """
        secret_id = self._call_context.params.get("SecretId")
        if secret_id and secret_id.startswith("arn:aws:secretsmanager:"):
            attributes[AWS_SECRETSMANAGER_SECRET_ARN] = secret_id

    def on_success(
        self,
        span: Span,
        result: _BotoResultT,
        instrumentor_context: _BotocoreInstrumentorContext,
    ):
        secret_arn = result.get("ARN")
        if secret_arn:
            span.set_attribute(AWS_SECRETSMANAGER_SECRET_ARN, secret_arn)
