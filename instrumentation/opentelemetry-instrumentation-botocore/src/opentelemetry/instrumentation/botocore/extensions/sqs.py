# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
import logging

from opentelemetry.instrumentation.botocore.extensions.types import (
    _AttributeMapT,
    _AwsSdkExtension,
    _BotocoreInstrumentorContext,
    _BotoResultT,
)
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.span import Span

_SUPPORTED_OPERATIONS = ["SendMessage", "SendMessageBatch", "ReceiveMessage"]

_logger = logging.getLogger(__name__)


class _SqsExtension(_AwsSdkExtension):
    def extract_attributes(self, attributes: _AttributeMapT):
        queue_url = self._call_context.params.get("QueueUrl")
        if queue_url:
            # TODO: update when semantic conventions exist
            attributes["aws.queue_url"] = queue_url
            attributes[SpanAttributes.MESSAGING_SYSTEM] = "aws.sqs"
            attributes[SpanAttributes.MESSAGING_URL] = queue_url
            try:
                attributes[SpanAttributes.MESSAGING_DESTINATION] = (
                    queue_url.split("/")[-1]
                )
            except IndexError:
                _logger.error(
                    "Could not extract messaging destination from '%s'",
                    queue_url,
                )

    def on_success(
        self,
        span: Span,
        result: _BotoResultT,
        instrumentor_context: _BotocoreInstrumentorContext,
    ):
        operation = self._call_context.operation
        if operation in _SUPPORTED_OPERATIONS:
            try:
                if operation == "SendMessage":
                    span.set_attribute(
                        SpanAttributes.MESSAGING_MESSAGE_ID,
                        result.get("MessageId"),
                    )
                elif operation == "SendMessageBatch" and result.get(
                    "Successful"
                ):
                    span.set_attribute(
                        SpanAttributes.MESSAGING_MESSAGE_ID,
                        result["Successful"][0]["MessageId"],
                    )
                elif operation == "ReceiveMessage" and result.get("Messages"):
                    span.set_attribute(
                        SpanAttributes.MESSAGING_MESSAGE_ID,
                        result["Messages"][0]["MessageId"],
                    )
            except (IndexError, KeyError):
                _logger.error("Could not extract the messaging message ID")
