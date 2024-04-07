import json
import sys
from typing import List
import boto3
import logging
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

# SQS Limit for each message is 256Kb - https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/quotas-messages.html
# 100 KB less than the limit to transport the last span
MAX_SQS_TO_SQS = 262144 - 100


# https://opentelemetry.io/docs/specs/otel/trace/sdk/#span-exporter
class AwsSqsSpanExporter(SpanExporter):
    def __init__(self, session: boto3.Session, sqs_queue_url: str) -> None:
        super().__init__()
        self.session = session
        self.logger = logging.getLogger(__name__)
        self.sqs_client = session.client("sqs")
        self.sqs_queue_url = sqs_queue_url

    def _get_size(self, span: dict) -> int:
        """This function recursively finds the size of a nested dictionary
        Args:
            span (dict): dictionary of spans to export
                         Eg: { 1: ReadableSpan }
        Returns:
            int: Size of dictionary
        """
        size = sys.getsizeof(span)
        for v in span.values():
            if isinstance(v, dict):
                size += self._get_size(v)
            else:
                size += sys.getsizeof(v)
        return size

    def _publish_message_to_sqs(self, message: str, attributes: dict):
        """Function used to submit jobs to SQS queue.

        Args:
            message (str): dictionary of messages
            attributes (dict): sqs message attributes
        """
        sqs_attributes = {}
        # Converting all attribute dictionary into SQS Message Attributes
        for i, v in attributes.items():
            sqs_attributes[i] = {"StringValue": v, "DataType": "String"}
        try:
            resp = self.sqs_client.send_message(
                QueueUrl=self.sqs_queue_url,
                MessageAttributes=sqs_attributes,
                MessageBody=json.dumps(message),
            )
            self.logger.info(f"Message deployed with id {resp['MessageId']}")
            return resp["MessageId"]

        except Exception as e:
            self.logger.error(f"Error publishing message to SQS: {e}")
            raise e

    def _compress_and_export_spans(self, spans: List[ReadableSpan]) -> None:
        """Function used to compress the spans into a single sqs message and export to SQS.
           This function also handles the 256Kb Message limit for SQS.
           It will break the messages into halfs if the limit if hit

        Args:
            spans (List[ReadableSpan]): List of Spans
        """
        compressed_spans = {}
        sqs_attributes = {}
        total_number_of_spans_per_sqs_message = 0
        self.logger.debug(f"Size of spans {len(spans)}")
        for span in spans:
            total_number_of_spans_per_sqs_message += 1
            compressed_spans[total_number_of_spans_per_sqs_message] = (
                json.loads(span.to_json())
            )
            size_of_spans = self._get_size(compressed_spans)
            # checking if the span size is not greater than SQS message limit
            if size_of_spans >= MAX_SQS_TO_SQS:
                sqs_attributes["number_of_spans"] = str(
                    total_number_of_spans_per_sqs_message
                )
                self._publish_message_to_sqs(compressed_spans, attributes)
                self.logger.info(
                    f"Spans exported to sqs {total_number_of_spans_per_sqs_message}"
                )
                # reseting it back to 0 for next batch
                total_number_of_spans_per_sqs_message = 0
                compressed_spans = {}
                attributes = {}

        # if we dont hit the limit we trigger with whenever we have collected
        attributes["number_of_spans"] = str(
            total_number_of_spans_per_sqs_message
        )
        self.logger.info(
            f"Limit not hit, transporting {total_number_of_spans_per_sqs_message} messages to sqs"
        )
        self._publish_message_to_sqs(compressed_spans, sqs_attributes)
        self.logger.info(
            f"Spans exported to sqs {total_number_of_spans_per_sqs_message}"
        )

    def export(self, batch_of_spans: List[ReadableSpan]):
        try:
            self._compress_and_export_spans(batch_of_spans)
            return SpanExportResult.SUCCESS
        except Exception as e:
            self.logger.error(f"Error exporting spans: {e}")
            return SpanExportResult.FAILURE
