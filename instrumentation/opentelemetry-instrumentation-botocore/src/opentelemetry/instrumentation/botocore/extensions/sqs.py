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
The OpenTelemetry botocore instrumentation provides enhanced support for SQS
by setting additional span attributes and injecting/extracting the trace context
to properly link spans.

The following SQS operations are automatically enhanced:

send_message / send_message_batch
---------------------------------

* Messaging span attributes are added according to the `messaging specification`_.
* The OpenTelemetry trace context is injected into the SQS MessageAttributes of
  each message, so the service receiving the message can link cascading spans
  to the trace which created the message.

receive_message
---------------

The ``receive_message`` operation returns a batch of message and typically
each message is then processed separately. According to the OpenTelemetry
`messaging specification`_, users of this instrumentation would expect so see
one span for the receive operation and a separate span for the processing of
each message.
The span for the ``receive_message`` operation is automatically created and span
attributes are set accordingly. Processing spans require some manual instrumentation.

Processing Spans
^^^^^^^^^^^^^^^^

The processing of SQS messages might differ per message. E.g. one message might
result in storing something to a DB, where another message might result in
calling an external HTTP endpoint.

For the botocore instrumentation it is not possible when the processing of an
SQS message starts, respectively ends. Thus, the processing operation needs to
be manually instrumented.
The botocore instrumentation provides the following means for tracing the
processing of SQS messages:

* `wrap_sqs_processing` decorator, to create the processing span for an arbitrary
  processing function that takes an SQS message as argument.
* `sqs_processing_span` context manager, to create the processing span for the
  scope where context manager is active.

The trace context is extracted from the SQS MessageAttributes and set on
the processing span's links accordingly. The parent of the processing span is
the span of the ``receive_message`` operation.

Integrating with SNS
^^^^^^^^^^^^^^^^^^^^

SQS queues can subscribe to SNS topics, so that the messages published to an SNS
topic is forwarded to the subscribed SQS queue. The form in which the SNS message
is forwarded to the SQS queue depends on the `raw message delivery`_ configuration
on the subscription.

* If raw message delivery is enabled the SNS message is
  forwarded to SQS as is. SNS MessageAttributes are converted into SQS
  MessageAttributes and are directly available on the SQS message.
* If raw message delivery is disabled (the default), the SNS message and its
  MessageAttributes is serialized as JSON string into the message body of the
  SQS message.

By default, the instrumentation, when creating the processing span, extracts the
trace context only from the MessageAttributes of the SQS message. To also extract
the trace context from the SQS message's body (and thus properly link the
processing span to the sender span) the ``extract_from_payload=True`` argument
needs to be passed to either the `wrap_sqs_processing` decorator or the
`sqs_processing_span` context manager.

.. _messaging Specification: https://github.com/open-telemetry/opentelemetry-specification/blob/master/specification/trace/semantic_conventions/messaging.md
.. _raw message delivery: https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html
"""

import abc
import contextlib
import functools
import inspect
import itertools
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    NamedTuple,
    Optional,
    TypeVar,
    cast,
)

from opentelemetry.instrumentation.botocore.extensions._messaging import (
    extract_propagation_context,
    inject_span_into_message,
)
from opentelemetry.instrumentation.botocore.extensions.types import (
    _AttributeMapT,
    _AwsSdkCallContext,
    _AwsSdkExtension,
    _BotoResultT,
)
from opentelemetry.propagate import get_global_textmap
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    MessagingOperationValues,
    SpanAttributes,
)
from opentelemetry.trace import Link, SpanKind, Tracer
from opentelemetry.trace.propagation import set_span_in_context
from opentelemetry.trace.span import INVALID_SPAN, Span

_messaging_system = "aws.sqs"
_sqs_msg_attr_key = "_otel_msg_ctx"


################################################################################
# common utils
################################################################################


def _add_common_attributes(
    attrs: _AttributeMapT, queue_url: Optional[str]
) -> Optional[str]:
    attrs[
        SpanAttributes.MESSAGING_DESTINATION_KIND
    ] = MessagingDestinationKindValues.QUEUE.value

    queue_name = None if not queue_url else queue_url.split("/")[-1]
    if queue_url:
        attrs[SpanAttributes.MESSAGING_DESTINATION] = queue_name
        attrs[SpanAttributes.MESSAGING_URL] = queue_url

    return queue_name


def _destination_name_from_url(queue_url: Optional[str]) -> Optional[str]:
    return None if not queue_url else queue_url.split("/")[-1]


class _PatchableDict(Dict):
    pass


class _SqsMessageContext(NamedTuple):
    tracer: Tracer
    receive_span: Span
    queue_url: str


################################################################################
# SQS operations
################################################################################


class _SqsOperation(abc.ABC):
    operation_name: str = None
    span_kind = SpanKind.CLIENT
    span_name_suffix: str = None

    @classmethod
    def extract_attributes(
        cls, call_context: _AwsSdkCallContext, attributes: _AttributeMapT
    ):
        queue_name = _add_common_attributes(
            attributes, call_context.params.get("QueueUrl")
        )
        if cls.span_name_suffix:
            call_context.span_name = (
                f"{queue_name or 'unknown'} {cls.span_name_suffix}"
            )

    @classmethod
    def before_service_call(cls, call_context: _AwsSdkCallContext, span: Span):
        pass

    @classmethod
    def on_response(
        cls, call_context: _AwsSdkCallContext, span: Span, result: _BotoResultT
    ):
        pass


class _OpSendMessage(_SqsOperation):
    operation_name = "SendMessage"
    span_kind = SpanKind.PRODUCER
    span_name_suffix = "send"

    @classmethod
    def before_service_call(cls, call_context: _AwsSdkCallContext, span: Span):
        inject_span_into_message(call_context.params)

    @classmethod
    def on_response(
        cls, call_context: _AwsSdkCallContext, span: Span, result: _BotoResultT
    ):
        span.set_attribute(
            SpanAttributes.MESSAGING_MESSAGE_ID, result.get("MessageId")
        )


class _OpSendMessageBatch(_SqsOperation):
    operation_name = "SendMessageBatch"
    span_kind = SpanKind.PRODUCER
    span_name_suffix = "send"

    @classmethod
    def before_service_call(cls, call_context: _AwsSdkCallContext, span: Span):
        for message in call_context.params.get("Entries") or ():
            inject_span_into_message(message)

    @classmethod
    def on_response(
        cls, call_context: _AwsSdkCallContext, span: Span, result: _BotoResultT
    ):
        # TODO: How to handle setting span attributes for multiple messages?
        pass


class _OpReceiveMessage(_SqsOperation):
    operation_name = "ReceiveMessage"
    span_kind = SpanKind.CONSUMER
    span_name_suffix = "receive"

    @classmethod
    def extract_attributes(
        cls, call_context: _AwsSdkCallContext, attributes: _AttributeMapT
    ):
        super().extract_attributes(call_context, attributes)

        attributes[
            SpanAttributes.MESSAGING_OPERATION
        ] = MessagingOperationValues.RECEIVE.value

        # make AWS deliver the attributes required for context propagation
        msg_attr_names = list(
            call_context.params.get("MessageAttributeNames") or ()
        )
        msg_attr_names.extend(get_global_textmap().fields)
        call_context.params["MessageAttributeNames"] = msg_attr_names

    @classmethod
    def on_response(
        cls, call_context: _AwsSdkCallContext, span: Span, result: _BotoResultT
    ):
        sqs_msg_ctx = _SqsMessageContext(
            call_context.tracer, span, call_context.params.get("QueueUrl")
        )
        result["Messages"] = [
            cls._patch_message(message, sqs_msg_ctx)
            for message in result.get("Messages") or ()
        ]

    @classmethod
    def _patch_message(
        cls, message: Dict[str, Any], sqs_msg_ctx: "_SqsMessageContext"
    ) -> "_PatchableDict":
        patchable_message = _PatchableDict(message)
        setattr(patchable_message, _sqs_msg_attr_key, sqs_msg_ctx)

        return patchable_message


################################################################################
# SQS extension
################################################################################

_OPERATION_MAPPING = {
    op.operation_name: op
    for op in globals().values()
    if inspect.isclass(op)
    and issubclass(op, _SqsOperation)
    and not inspect.isabstract(op)
}  # type: Dict[str, _SqsOperation]


class _SqsExtension(_AwsSdkExtension):
    def __init__(self, call_context: _AwsSdkCallContext):
        super().__init__(call_context)
        self._op = _OPERATION_MAPPING.get(call_context.operation)
        if self._op:
            call_context.span_kind = self._op.span_kind

    def extract_attributes(self, attributes: _AttributeMapT):
        attributes[SpanAttributes.MESSAGING_SYSTEM] = _messaging_system

        if self._op:
            self._op.extract_attributes(self._call_context, attributes)

    def before_service_call(self, span: Span):
        if self._op:
            self._op.before_service_call(self._call_context, span)

    def on_success(self, span: Span, result: _BotoResultT):
        if self._op:
            self._op.on_response(self._call_context, span, result)


################################################################################
# Processing received SQS messages
################################################################################


@contextlib.contextmanager
def sqs_processing_span(
    message: Dict[str, Any], extract_from_payload: bool = False
) -> Iterator[Span]:
    """A context manager to trace the processing of a received SQS message.

    Example::

        import botocore
        from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
        from opentelemetry.instrumentation.botocore.extensions.sqs import sqs_processing_span

        BotocoreInstrumentor().instrument()

        session = botocore.session.get_session()
        session.set_credentials(access_key="access-key", secret_key="secret-key")
        client = self.client = session.create_client("sqs", region_name="us-west-2")

        result = self.client.receive_message(QueueUrl='<queue-url>')
        for message in result["Messages"]:
            with sqs_processing_span(message):
                # message processing goes here
                pass

    Args:
        message: the SQS message to trace
        extract_from_payload: AWS delivers SNS messages as payload in the SQS
            message body when an SQS queue is subscribed to an SNS topic and
            ``raw message delivery`` is disabled. Set this parameter to ``True``
            to extract the propagation context from the payload of the SQS message.
    """
    msg_ctx = getattr(
        message, _sqs_msg_attr_key, None
    )  # type: Optional[_SqsMessageContext]
    if not msg_ctx:
        yield INVALID_SPAN
        return

    attrs = {
        SpanAttributes.MESSAGING_SYSTEM: _messaging_system,
        SpanAttributes.MESSAGING_OPERATION: MessagingOperationValues.PROCESS.value,
        SpanAttributes.MESSAGING_MESSAGE_ID: message.get("MessageId"),
    }
    queue_name = _add_common_attributes(attrs, msg_ctx.queue_url)

    parent_ctx = set_span_in_context(msg_ctx.receive_span)
    link_span = extract_propagation_context(message, extract_from_payload)

    links = ()
    link_span_ctx = link_span.get_span_context()
    if link_span_ctx.is_valid:
        links = [Link(link_span_ctx)]

    with msg_ctx.tracer.start_as_current_span(
        f"{queue_name or 'unknown'} process",
        parent_ctx,
        SpanKind.CONSUMER,
        attributes=attrs,
        links=links,
    ) as span:
        yield span


_ProcessFuncT = TypeVar("_ProcessFuncT", bound=Callable[..., Any])


def wrap_sqs_processing(
    func: _ProcessFuncT = None, extract_from_payload: bool = False
) -> _ProcessFuncT:
    """A decorator to trace the processing of received SQS messages.

    The SQS message can be anywhere in the parameter list of the decorated
    function. The decorator will automatically detect the SQS message and create
    a corresponding processing span.

    Example::

        import botocore
        from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
        from opentelemetry.instrumentation.botocore.extensions.sqs import wrap_sqs_processing

        BotocoreInstrumentor().instrument()

        session = botocore.session.get_session()
        session.set_credentials(access_key="access-key", secret_key="secret-key")
        client = self.client = session.create_client("sqs", region_name="us-west-2")

        @wrap_sqs_processing()
        def process_sqs_message(message):
            # message processing goes here
            pass

        result = self.client.receive_message(QueueUrl='<queue-url>')
        for message in result["Messages"]:
            process_sqs_message(message)

    Args:
        func: the processing function to decorate
        extract_from_payload: AWS delivers SNS messages as payload in the SQS
            message body when an SQS queue is subscribed to an SNS topic and
            ``raw message delivery`` is disabled. Set this parameter to ``True``
            to extract the propagation context from the payload of the SQS message.
    """
    if func is None:
        return functools.partial(
            wrap_sqs_processing, extract_from_payload=extract_from_payload
        )

    if not callable(func):
        return cast(_ProcessFuncT, func)

    @functools.wraps(func)
    def _wrapper(*wargs, **wkwargs):
        message = None
        for arg in itertools.chain(wargs, wkwargs.values()):
            if getattr(arg, _sqs_msg_attr_key, None):
                message = arg
                break

        with sqs_processing_span(message, extract_from_payload):
            return func(*wargs, **wkwargs)

    return cast(_ProcessFuncT, _wrapper)
