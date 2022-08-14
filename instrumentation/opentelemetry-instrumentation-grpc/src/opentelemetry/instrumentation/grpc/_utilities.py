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
from typing import Callable, Dict, Generator, Iterable, Iterator, NoReturn, Optional

import grpc
from opentelemetry import metrics, trace
from opentelemetry.instrumentation.grpc._types import ProtoMessage
from opentelemetry.semconv.trace import MessageTypeValues, SpanAttributes
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.types import Attributes, Metadata


_MESSAGE: str = "message"
"""Event name of a message."""


def _add_message_event(
    active_span: trace.Span,
    message_type: str,
    message_size_by: int,
    message_id: int = 1
) -> None:
    """Adds a message event of an RPC to an active span.

    Args:
        active_span (trace.Span): The active span in which to record the
            message as event.
        message_type (str): The message type value as str, either "SENT" or
            "RECEIVED".
        message_size_by (int): The (uncompressed) message size in bytes.
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


def _get_status_code(context: grpc.RpcContext) -> grpc.StatusCode:
    """Extracts the status code from a context, even though the context is a
    ServicerContext of a grpc version which does not support code().

    Args:
        context (grpc.RpcContext): The context to extract the status code from.

    Returns:
        grpc.StatusCode: The extracted status code.
    """

    try:
        code = context.code()
    except RuntimeError:
        if isinstance(code, _OpenTelemetryServicerContext):
            code = context._code
        elif isinstance(code, grpc.ServicerContext):
            code = context._state._code
        else:
            raise

    if code is not None:
        return code

    return grpc.StatusCode.OK


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

    def __init__(self, meter: metrics.Meter, kind: _MetricKind) -> None:
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
        active_span: trace.Span,
        request: ProtoMessage,
        message_type: MessageTypeValues,
        metric_attributes: Attributes
    ) -> None:
        """Records a unary request.

        The request is recorded as event, its size in the request-size-
        histogram and a one for a unary request in the requests-per-RPC-
        histogram.

        Args:
            active_span (trace.Span): The active span in which to record the
                request message as event.
            request (ProtoMessage): The request message.
            message_type (MessageTypeValues): The message type value.
            metric_attributes (Attributes): The attributes to record in the
                metrics.
        """

        message_size_by = request.ByteSize()
        _add_message_event(active_span, message_type.value, message_size_by)
        self._request_size_histogram.record(message_size_by, metric_attributes)
        self._requests_per_rpc_histogram.record(1, metric_attributes)

    def _record_unary_or_streaming_response(
        self,
        active_span: trace.Span,
        response: ProtoMessage,
        message_type: MessageTypeValues,
        metric_attributes: Attributes,
        response_id: int = 1
    ) -> None:
        """Records a unary OR a single, streaming response.

        The response is recorded as event and its size in the response-size-
        histogram.

        Args:
            active_span (trace.Span): The active span in which to record the
                response message as event.
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

    def _record_num_of_responses_per_rpc(
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
        active_span: trace.Span,
        response: ProtoMessage,
        message_type: MessageTypeValues,
        metric_attributes: Attributes
    ) -> None:
        """Records a unary response.

        The response is recorded as event, its size in the response-size-
        histogram and a one for a unary response in the responses-per-RPC-
        histogram.

        Args:
            active_span (trace.Span): The active span in which to record the
                response message as event.
            response (ProtoMessage): The response message.
            message_type (MessageTypeValues): The message type value.
            metric_attributes (Attributes): The attributes to record in the
                metrics.
        """

        self._record_unary_or_streaming_response(
            active_span, response, message_type, metric_attributes
        )
        self._record_num_of_responses_per_rpc(1, metric_attributes)

    def _record_streaming_request(
        self,
        active_span: trace.Span,
        request_iterator: Iterator[ProtoMessage],
        message_type: MessageTypeValues,
        metric_attributes: Attributes
    ) -> Iterator[ProtoMessage]:
        """Records a streaming request.

        The requests are recorded as events, their size in the request-size-
        histogram and the total number of requests in the requests-per-RPC-
        histogram.

        Args:
            active_span (trace.Span): The active span in which to record the
                request messages as event.
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
        active_span: trace.Span,
        response_iterator: Iterator[ProtoMessage],
        message_type: MessageTypeValues,
        metric_attributes: Attributes
    ) -> Iterator[ProtoMessage]:
        """Records a streaming response.

        The responses are recorded as events, their size in the response-size-
        histogram and the total number of responses in the responses-per-RPC-
        histogram.

        Args:
            active_span (trace.Span): The active span in which to record the
                response messages as event.
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
                self._record_unary_or_streaming_response(
                    active_span,
                    response,
                    message_type,
                    metric_attributes,
                    response_id=res_id
                )
                yield response
        finally:
            self._record_num_of_responses_per_rpc(res_id, metric_attributes)

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
        code = _get_status_code(context)
        metric_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = code.value[0]
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
            code = _get_status_code(context)
            metric_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = (
                code.value[0]
            )
            self._duration_histogram.record(duration, metric_attributes)


# pylint:disable=abstract-method
class _OpenTelemetryServicerContext(grpc.ServicerContext):

    def __init__(
        self,
        servicer_context: grpc.ServicerContext,
        active_span: trace.Span
    ) -> None:
        self._servicer_context = servicer_context
        self._active_span = active_span
        self._code = grpc.StatusCode.OK
        self._details = None
        super().__init__()

    def __getattr__(self, attr):
        return getattr(self._servicer_context, attr)

    # Interface of grpc.RpcContext

    def add_callback(self, callback: Callable[[], None]) -> None:
        return self._servicer_context.add_callback(callback)

    def cancel(self) -> bool:
        self._code = grpc.StatusCode.CANCELLED
        self._details = grpc.StatusCode.CANCELLED.value[1]
        self._active_span.set_attribute(
            SpanAttributes.RPC_GRPC_STATUS_CODE, self._code.value[0]
        )
        self._active_span.set_status(
            Status(
                status_code=StatusCode.ERROR,
                description=f"{self._code}: {self._details}",
            )
        )
        return self._servicer_context.cancel()

    def is_active(self) -> bool:
        return self._servicer_context.is_active()

    def time_remaining(self) -> Optional[float]:
        return self._servicer_context.time_remaining()

    # Interface of grpc.ServicerContext

    def abort(self, code: grpc.StatusCode, details: str) -> NoReturn:
        if not hasattr(self._servicer_context, "abort"):
            raise RuntimeError(
                "abort() is not supported with the installed version of grpcio"
            )
        self._code = code
        self._details = details
        self._active_span.set_attribute(
            SpanAttributes.RPC_GRPC_STATUS_CODE, code.value[0]
        )
        self._active_span.set_status(
            Status(
                status_code=StatusCode.ERROR,
                description=f"{code}: {details}",
            )
        )
        return self._servicer_context.abort(code, details)

    def abort_with_status(self, status: grpc.Status) -> NoReturn:
        if not hasattr(self._servicer_context, "abort_with_status"):
            raise RuntimeError(
                "abort_with_status() is not supported with the installed "
                "version of grpcio"
            )
        return self._servicer_context.abort_with_status(status)

    def auth_context(self) -> Dict[str, Iterable[bytes]]:
        return self._servicer_context.auth_context()

    def code(self) -> grpc.StatusCode:
        if not hasattr(self._servicer_context, "code"):
            raise RuntimeError(
                "code() is not supported with the installed version of grpcio"
            )
        return self._servicer_context.code()

    def details(self) -> str:
        if not hasattr(self._servicer_context, "details"):
            raise RuntimeError(
                "details() is not supported with the installed version of "
                "grpcio"
            )
        return self._servicer_context.details()

    def disable_next_message_compression(self) -> None:
        return self._service_context.disable_next_message_compression()

    def invocation_metadata(self) -> Metadata:
        return self._servicer_context.invocation_metadata()

    def peer(self) -> str:
        return self._servicer_context.peer()

    def peer_identities(self) -> Optional[Iterable[bytes]]:
        return self._servicer_context.peer_identities()

    def peer_identity_key(self) -> Optional[str]:
        return self._servicer_context.peer_identity_key()

    def send_initial_metadata(self, initial_metadata: Metadata) -> None:
        return self._servicer_context.send_initial_metadata(initial_metadata)

    def set_code(self, code: grpc.StatusCode) -> None:
        self._code = code
        # use details if we already have it, otherwise the status description
        details = self._details or code.value[1]
        self._active_span.set_attribute(
            SpanAttributes.RPC_GRPC_STATUS_CODE, code.value[0]
        )
        if code != grpc.StatusCode.OK:
            self._active_span.set_status(
                Status(
                    status_code=StatusCode.ERROR,
                    description=f"{code}: {details}",
                )
            )
        return self._servicer_context.set_code(code)

    def set_compression(self, compression: grpc.Compression) -> None:
        return self._servicer_context.set_compression(compression)

    def set_details(self, details: str) -> None:
        self._details = details
        if self._code != grpc.StatusCode.OK:
            self._active_span.set_status(
                Status(
                    status_code=StatusCode.ERROR,
                    description=f"{self._code}: {details}",
                )
            )
        return self._servicer_context.set_details(details)

    def set_trailing_metadata(self, trailing_metadata: Metadata) -> None:
        return self._servicer_context.set_trailing_metadata(trailing_metadata)

    def trailing_metadata(self) -> Metadata:
        return self._servicer_context.trailing_metadata()
