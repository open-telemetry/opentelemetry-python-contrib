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
"""
Instrument `boto3sqs`_ to trace SQS applications.

.. _boto3sqs: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sqs.html


Usage
-----

.. code:: python

    import boto3
    from opentelemetry.instrumentation.boto3sqs import Boto3SQSInstrumentor


    Boto3SQSInstrumentor().instrument()
"""

import wrapt
import logging
import boto3
import botocore.client
from typing import Dict, Collection, List, Optional, Any, Tuple
from opentelemetry import context, propagate, trace
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.boto3sqs.version import __version__
from opentelemetry.instrumentation.boto3sqs.package import _instruments
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.propagators.textmap import Getter, Setter, CarrierT
from opentelemetry.trace import SpanKind, Tracer, Span, TracerProvider, Link
from opentelemetry.semconv.trace import (
    MessagingOperationValues,
    SpanAttributes,
    MessagingDestinationKindValues,
)

logger = logging.getLogger(__name__)
OPENTELEMETRY_ATTRIBUTE_IDENTIFIER = "otel."


class Boto3SQSGetter(Getter):
    def get(self, carrier: CarrierT, key: str) -> Optional[List[str]]:
        if not (
            value := carrier.get(
                f"{OPENTELEMETRY_ATTRIBUTE_IDENTIFIER}{key}", {}
            )
        ):
            return None
        return [value.get("StringValue", None)]

    def keys(self, carrier: CarrierT) -> List[str]:
        return [
            key.rstrip(OPENTELEMETRY_ATTRIBUTE_IDENTIFIER)
            if key.startswith(OPENTELEMETRY_ATTRIBUTE_IDENTIFIER)
            else key
            for key in carrier.keys()
        ]


class Boto3SQSSetter(Setter):
    def set(self, carrier: CarrierT, key: str, value: str) -> None:
        if len(carrier.items()) < 10:
            carrier[f"{OPENTELEMETRY_ATTRIBUTE_IDENTIFIER}{key}"] = {
                "StringValue": value,
                "DataType": "String",
            }
        else:
            logger.warning(
                "Boto3 SQS instrumentation: cannot set context propagation on SQS/SNS message due to maximum amount of "
                "MessageAttributes"
            )


boto3sqs_getter = Boto3SQSGetter()
boto3sqs_setter = Boto3SQSSetter()


class Boto3SQSInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    @staticmethod
    def _enrich_span(
        span: Span,
        queue_name: str,
        conversation_id: Optional[str] = None,
        operation: Optional[MessagingOperationValues] = None,
        message_id: Optional[str] = None,
    ) -> None:
        if not span.is_recording():
            return
        span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "aws.sqs")
        span.set_attribute(
            SpanAttributes.MESSAGING_DESTINATION_KIND,
            MessagingDestinationKindValues.QUEUE.value,
        )
        if operation:
            span.set_attribute(
                SpanAttributes.MESSAGING_OPERATION, operation.value
            )
        else:
            span.set_attribute(SpanAttributes.MESSAGING_TEMP_DESTINATION, True)
        span.set_attribute(SpanAttributes.MESSAGING_DESTINATION, queue_name)
        if conversation_id:
            span.set_attribute(
                SpanAttributes.MESSAGING_CONVERSATION_ID, conversation_id
            )
        if message_id:
            span.set_attribute(SpanAttributes.MESSAGING_MESSAGE_ID, message_id)

    @staticmethod
    def _extract_queue_name_from_url(queue_url: str) -> str:
        # A Queue name cannot have the `/` char, therefore we can return the part after the last /
        return queue_url.split("/")[-1]

    def _wrap_send_message(self) -> None:
        def send_wrapper(wrapped, instance, args, kwargs):
            if context.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
                return wrapped(*args, **kwargs)
            queue_url = kwargs.get("QueueUrl")
            # The method expect QueueUrl and Entries params, so if they are None, we call wrapped to receive the
            # original exception
            queue_name = Boto3SQSInstrumentor._extract_queue_name_from_url(
                queue_url
            )
            span = self._tracer.start_span(
                name=f"{queue_name} send",
                kind=SpanKind.PRODUCER,
            )
            if span.is_recording():
                Boto3SQSInstrumentor._enrich_span(span, queue_name)
            with trace.use_span(span, end_on_exit=True):
                attributes = kwargs.pop("MessageAttributes", {})
                propagate.inject(attributes, setter=boto3sqs_setter)
                retval = wrapped(*args, MessageAttributes=attributes, **kwargs)
                if message_id := retval.get("MessageId"):
                    span.set_attribute(
                        SpanAttributes.MESSAGING_MESSAGE_ID, message_id
                    )
                return retval

        wrapt.wrap_function_wrapper(
            self._sqs_class, "send_message", send_wrapper
        )

    def _wrap_send_message_batch(self) -> None:
        def send_batch_wrapper(wrapped, instance, args, kwargs):
            queue_url = kwargs.get("QueueUrl")
            entries = kwargs.get("Entries")
            # The method expect QueueUrl and Entries params, so if they are None, we call wrapped to receive the
            # origial exception
            if (
                context.get_value(_SUPPRESS_INSTRUMENTATION_KEY)
                or not queue_url
                or not entries
            ):
                return wrapped(*args, **kwargs)
            queue_name = Boto3SQSInstrumentor._extract_queue_name_from_url(
                queue_url
            )
            ids_to_spans: Dict[str, Span] = {}
            for entry in entries:
                entry_id = entry["Id"]
                span = self._tracer.start_span(
                    name=f"{queue_name} send",
                    kind=SpanKind.PRODUCER,
                )
                ids_to_spans[entry_id] = span
                if span.is_recording():
                    Boto3SQSInstrumentor._enrich_span(
                        span, queue_name, conversation_id=entry_id
                    )
                with trace.use_span(span):
                    if "MessageAttributes" not in entry:
                        entry["MessageAttributes"] = {}
                    propagate.inject(
                        entry["MessageAttributes"], setter=boto3sqs_setter
                    )
            retval = wrapped(*args, **kwargs)
            for successful_messages in retval["Successful"]:
                message_identifier = successful_messages["Id"]
                if message_span := ids_to_spans.get(message_identifier):
                    message_span.set_attribute(
                        SpanAttributes.MESSAGING_MESSAGE_ID,
                        successful_messages.get("MessageId"),
                    )
            for span in ids_to_spans.values():
                span.end()
            return retval

        wrapt.wrap_function_wrapper(
            self._sqs_class, "send_message_batch", send_batch_wrapper
        )

    def _wrap_receive_message(self) -> None:
        def receive_message_wrapper(wrapped, instance, args, kwargs):
            queue_url = kwargs.get("QueueUrl")
            message_attribute_names = kwargs.pop("MessageAttributeNames", [])
            message_attribute_names.append(
                f"{OPENTELEMETRY_ATTRIBUTE_IDENTIFIER}*"
            )
            queue_name = Boto3SQSInstrumentor._extract_queue_name_from_url(
                queue_url
            )
            with self._tracer.start_as_current_span(name=f"{queue_name} receive", end_on_exit=True) as span:
                Boto3SQSInstrumentor._enrich_span(
                    span, queue_name
                )
                retval = wrapped(
                    *args, MessageAttributeNames=message_attribute_names, **kwargs
                )
                messages = retval.get("Messages", [])
                for message in messages:
                    if not (receipt_handle := message["ReceiptHandle"]):
                        continue
                    if receipt_handle in self._received_messages_spans:
                        span, token = self._received_messages_spans[receipt_handle]
                        context.detach(token)
                        span.end()
                    message_attributes = message.get("MessageAttributes", {})
                    links = []
                    if ctx := propagate.extract(
                        message_attributes, getter=boto3sqs_getter
                    ):
                        for item in ctx.values():
                            if hasattr(item, "get_span_context"):
                                links.append(Link(context=item.get_span_context()))
                    span = self._tracer.start_span(
                        name=f"{queue_name} produce",
                        links=links,
                        kind=SpanKind.CONSUMER,
                    )
                    with trace.use_span(span):
                        new_context = trace.set_span_in_context(span, ctx)
                        token = context.attach(new_context)
                        message_id = message.get("MessageId", None)
                        self._received_messages_spans[receipt_handle] = (
                            span,
                            token,
                        )
                        Boto3SQSInstrumentor._enrich_span(
                            span, queue_name, message_id=message_id
                        )
            return retval

        wrapt.wrap_function_wrapper(
            self._sqs_class, "receive_message", receive_message_wrapper
        )

    def _wrap_delete_message(self) -> None:
        def delete_message_wrapper(wrapped, instance, args, kwargs):
            if receipt_handle := kwargs.get("ReceiptHandle"):
                if receipt_handle in self._received_messages_spans:
                    span, token = self._received_messages_spans[receipt_handle]
                    context.detach(token)
                    span.end()
            return wrapped(*args, **kwargs)

        wrapt.wrap_function_wrapper(
            self._sqs_class, "delete_message", delete_message_wrapper
        )

    def _wrap_client_creation(self) -> None:
        """
        Since botocore creates classes on the fly using schemas, the SQS class is not necesraily created upon the call
        of `instrument()`. Therefore we need to wrap the creation of the boto3 client, which triggers the creation of
        the SQS client.
        """

        def client_wrapper(wrapped, instance, args, kwargs):
            retval = wrapped(*args, **kwargs)
            if not self._did_decorate:
                self._decorate_sqs()
            return retval

        wrapt.wrap_function_wrapper(boto3, "client", client_wrapper)

    def _decorate_sqs(self) -> None:
        """
        Since botocore creates classes on the fly using schemas, we try to find the class that inherits from the base
        class and defines SQS to wrap.
        """
        sqs_class = [
            cls
            for cls in botocore.client.BaseClient.__subclasses__()
            if "botocore.client.SQS" in str(cls)
        ]
        if sqs_class:
            self._sqs_class = sqs_class[0]
            self._did_decorate = True
            self._wrap_send_message()
            self._wrap_send_message_batch()
            self._wrap_receive_message()
            self._wrap_delete_message()

    def _un_decorate_sqs(self) -> None:
        if self._did_decorate:
            unwrap(self._sqs_class, "send_message")
            unwrap(self._sqs_class, "send_message_batch")
            unwrap(self._sqs_class, "receive_message")
            unwrap(self._sqs_class, "delete_message")
            self._did_decorate = False

    def _instrument(self, **kwargs: Dict[str, Any]) -> None:
        self._did_decorate: bool = False
        self._received_messages_spans: Dict[str, Tuple[Span, Any]] = {}
        self._tracer_provider: Optional[TracerProvider] = kwargs.get(
            "tracer_provider"
        )
        self._tracer: Tracer = trace.get_tracer(
            __name__, __version__, self._tracer_provider
        )
        self._wrap_client_creation()
        self._decorate_sqs()

    def _uninstrument(self, **kwargs: Dict[str, Any]) -> None:
        unwrap(boto3, "client")
        self._un_decorate_sqs()
