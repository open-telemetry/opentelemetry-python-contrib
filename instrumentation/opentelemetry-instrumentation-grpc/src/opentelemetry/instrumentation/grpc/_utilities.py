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

"""Internal utilities."""

from collections import namedtuple
from contextlib import contextmanager
from enum import Enum
from timeit import default_timer
from typing import Generator, Iterator

import grpc
from opentelemetry.instrumentation.grpc._types import  ProtoMessage
from opentelemetry.metrics import Meter
from opentelemetry.trace import Span
from opentelemetry.semconv.trace import MessageTypeValues, SpanAttributes
from opentelemetry.util.types import Attributes


_MESSAGE: str = "message"
"""Event name of a message."""


def _add_message_event(
    active_span: Span,
    message_type: str,
    message_size_by: int,
    message_id: int = 1
) -> None:
    """Adds a message event of an RPC to an active span.

    Args:
        active_span (Span): The active span in which to record the message
            as event.
        message_type (str): The message type value as str, either "SENT" or
            "RECEIVED".
        message_size_by (int): The (uncompressed) message size in bytes as int.
        message_id (int, optional): The message ID. Defaults to 1.
    """

    active_span.add_event(
        _MESSAGE,
        {
            SpanAttributes.MESSAGE_TYPE: message_type,
            SpanAttributes.MESSAGE_ID: message_id,
            SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: message_size_by,
        }
    )


class _ClientCallDetails(
        namedtuple(
            "_ClientCallDetails",
            ("method", "timeout", "metadata", "credentials",
             "wait_for_ready", "compression")
        ),
        grpc.ClientCallDetails
):
    pass


class _MetricKind(Enum):
    """Specifies the kind of the metric.
    """

    #: Indicates that the metric is of a server.
    CLIENT = "client"

    #: Indicates that the metric is of a server.
    SERVER = "server"


class _EventMetricRecorder:
    """Internal class for recording messages as event and in the histograms
    and for recording the duration of a RPC.
    """

    def __init__(self, meter: Meter, kind: _MetricKind) -> None:
        """Initializes the _EventMetricRecorder.

        Args:
            meter (Meter): The meter to create the metrics.
            kind (str): The kind of the metric recorder, either for a "client"
                or "server".
        """

        self._meter = meter

        metric_kind = _MetricKind(kind)
        self._duration_histogram = self._meter.create_histogram(
            name=f"rpc.{metric_kind.value}.duration",
            unit="ms",
            description="Measures duration of RPC",
        )
        self._request_size_histogram = self._meter.create_histogram(
            name=f"rpc.{metric_kind.value}.request.size",
            unit="By",
            description="Measures size of RPC request messages (uncompressed)",
        )
        self._response_size_histogram = self._meter.create_histogram(
            name=f"rpc.{metric_kind.value}.response.size",
            unit="By",
            description="Measures size of RPC response messages "
                        "(uncompressed)",
        )
        self._requests_per_rpc_histogram = self._meter.create_histogram(
            name=f"rpc.{metric_kind.value}.requests_per_rpc",
            unit="1",
            description="Measures the number of messages received per RPC. "
                        "Should be 1 for all non-streaming RPCs",
        )
        self._responses_per_rpc_histogram = self._meter.create_histogram(
            name=f"rpc.{metric_kind.value}.responses_per_rpc",
            unit="1",
            description="Measures the number of messages sent per RPC. "
                        "Should be 1 for all non-streaming RPCs",
        )

    def _record_unary_request(
        self,
        active_span: Span,
        request: ProtoMessage,
        message_type: MessageTypeValues,
        metric_attributes: Attributes
    ) -> None:
        """Records a unary request.

        The request is recorded as event, its size in the request-size-
        histogram and a one for a unary request in the requests-per-RPC-
        histogram.

        Args:
            active_span (Span): The active span in which to record the request
                as event.
            request (ProtoMessage): The request message.
            message_type (MessageTypeValues): The message type value.
            metric_attributes (Attributes): The attributes to record in the
                metrics.
        """

        message_size_by = request.ByteSize()
        _add_message_event(active_span, message_type.value, message_size_by)
        self._request_size_histogram.record(message_size_by, metric_attributes)
        self._requests_per_rpc_histogram.record(1, metric_attributes)

    def _record_response(
        self,
        active_span: Span,
        response: ProtoMessage,
        message_type: MessageTypeValues,
        metric_attributes: Attributes,
        response_id: int = 1
    ) -> None:
        """Records a unary OR streaming response.

        The response is recorded as event and its size in the response-size-
        histogram.

        Args:
            active_span (Span): The active span in which to record the response
                as event.
            response (ProtoMessage): The response message.
            message_type (MessageTypeValues): The message type value.
            metric_attributes (Attributes): The attributes to record in the
                metrics.
            response_id (int, optional): The response ID. Defaults to 1.
        """

        message_size_by = response.ByteSize()
        _add_message_event(
            active_span,
            message_type.value,
            message_size_by,
            message_id=response_id
        )
        self._response_size_histogram.record(
            message_size_by, metric_attributes
        )

    def _record_responses_per_rpc(
        self,
        responses_per_rpc: int,
        metric_attributes: Attributes
    ) -> None:
        """Records the number of responses in the responses-per-RPC-histogram
        for a streaming response.


        Args:
            responses_per_rpc (int): The number of responses.
            metric_attributes (Attributes):  The attributes to record in the
                metric.
        """

        self._responses_per_rpc_histogram.record(
            responses_per_rpc, metric_attributes
        )

    def _record_unary_response(
        self,
        active_span: Span,
        response: ProtoMessage,
        message_type: MessageTypeValues,
        metric_attributes: Attributes
    ) -> None:
        """Records a unary response.

        The response is recorded as event, its size in the response-size-
        histogram and a one for a unary response in the responses-per-RPC-
        histogram.

        Args:
            active_span (Span): The active span in which to record the response
                as event.
            response (ProtoMessage): The response message.
            message_type (MessageTypeValues): The message type value.
            metric_attributes (Attributes): The attributes to record in the
                metrics.
        """

        self._record_response(
            active_span, response, message_type, metric_attributes
        )
        self._record_responses_per_rpc(1, metric_attributes)

    def _record_streaming_request(
        self,
        active_span: Span,
        request_iterator: Iterator[ProtoMessage],
        message_type: MessageTypeValues,
        metric_attributes: Attributes
    ) -> Iterator[ProtoMessage]:
        """Records a streaming request.

        The requests are recorded as events, their size in the request-size-
        histogram and the total number of requests in the requests-per-RPC-
        histogram.

        Args:
            active_span (Span): The active span in which to record the request
                as event.
            request_iterator (Iterator[ProtoMessage]): The iterator over the
                request messages.
            message_type (MessageTypeValues): The message type value.
            metric_attributes (Attributes): The attributes to record in the
                metrics.

        Yields:
            Iterator[ProtoMessage]:  The iterator over the recorded request
                messages.
        """

        try:
            req_id = 0
            for req_id, request in enumerate(request_iterator, start=1):
                message_size_by = request.ByteSize()
                _add_message_event(
                    active_span,
                    message_type.value,
                    message_size_by,
                    message_id=req_id
                )
                self._request_size_histogram.record(
                    message_size_by, metric_attributes
                )
                yield request
        finally:
            self._requests_per_rpc_histogram.record(req_id, metric_attributes)

    def _record_streaming_response(
        self,
        active_span: Span,
        response_iterator: Iterator[ProtoMessage],
        message_type: MessageTypeValues,
        metric_attributes: Attributes
    ) -> Iterator[ProtoMessage]:
        """Records a streaming response.

        The responses are recorded as events, their size in the response-size-
        histogram and the total number of responses in the responses-per-RPC-
        histogram.

        Args:
            active_span (Span): The active span in which to record the response
                as event.
            response_iterator (Iterator[ProtoMessage]): The iterator over the
                response messages.
            message_type (MessageTypeValues): The message type value.
            metric_attributes (Attributes): The attributes to record in the
                metrics.

        Yields:
            Iterator[ProtoMessage]:  The iterator over the recorded response
                messages.
        """

        try:
            res_id = 0
            for res_id, response in enumerate(response_iterator, start=1):
                self._record_response(
                    active_span,
                    response,
                    message_type,
                    metric_attributes,
                    response_id=res_id
                )
                yield response
        finally:
            self._record_responses_per_rpc(res_id, metric_attributes)

    def _start_duration_measurement(self) -> float:
        """Starts a duration measurement and returns the start time.

        Returns:
            float: The start time.
        """

        return default_timer()

    def _record_duration(
        self,
        start_time: float,
        metric_attributes: Attributes,
        context: grpc.RpcContext
    ) -> None:
        """Records a duration of an RPC in the duration histogram. The duration
        is calculated as difference between the call of this method and the
        start time which has been returned by _start_duration_measurement.d

        Args:
            start_time (float): The start time.
            metric_attributes (Attributes): The attributes to record in the
                metric.
            context (grpc.RpcContext): The RPC context to update the status
                code of the RPC.
        """

        duration = max(round((default_timer() - start_time) * 1000), 0)
        if context.code() in (None, grpc.StatusCode.OK):
            metric_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = (
                grpc.StatusCode.OK.value[0]
            )
        else:
            metric_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = (
                context.code().value[0]
            )
        self._duration_histogram.record(duration, metric_attributes)

    @contextmanager
    def _record_duration_manager(
        self,
        metric_attributes: Attributes,
        context: grpc.RpcContext
    ) -> Generator[None, None, None]:
        """Returns a context manager to measure the duration of an RPC in the
        duration histogram.

        Args:
            metric_attributes (Attributes): The attributes to record in the
                metric.
            context (grpc.RpcContext): The RPC context to update the status
                code of the RPC.

        Yields:
            Generator[None, None, None]: The context manager.
        """

        start_time = default_timer()
        try:
            yield
        finally:
            duration = max(round((default_timer() - start_time) * 1000), 0)
            if context.code() in (None, grpc.StatusCode.OK):
                metric_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = (
                    grpc.StatusCode.OK.value[0]
                )
            else:
                metric_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = (
                    context.code().value[0]
                )
            self._duration_histogram.record(duration, metric_attributes)
