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

# pylint:disable=relative-beyond-top-level
# pylint:disable=arguments-differ
# pylint:disable=no-member
# pylint:disable=signature-differs

"""Implementation of the invocation-side open-telemetry interceptor."""

from collections import OrderedDict
from typing import Callable, Iterator, MutableMapping

import grpc

from opentelemetry import context, trace
from opentelemetry.instrumentation.grpc._types import ProtoMessage
from opentelemetry.instrumentation.grpc._utilities import (
    _ClientCallDetails,
    _EventMetricRecorder,
    _MetricKind,
    _OpentelemetryResponseIterator,
)
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.propagate import inject
from opentelemetry.propagators.textmap import Setter
from opentelemetry.semconv.trace import (
    MessageTypeValues,
    RpcSystemValues,
    SpanAttributes,
)
from opentelemetry.trace import Span
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.types import Attributes


class _CarrierSetter(Setter):
    """We use a custom setter in order to be able to lower case
    keys as is required by grpc.
    """

    def set(
        self, carrier: MutableMapping[str, str], key: str, value: str
    ) -> None:
        carrier[key.lower()] = value


_carrier_setter = _CarrierSetter()


def _make_future_done_callback(
    span: Span,
    metric_recorder: _EventMetricRecorder,
    attributes: Attributes,
    start_time: float,
) -> Callable[[grpc.Future], None]:
    def callback(response_future: grpc.Future) -> None:
        with trace.use_span(
            span,
            record_exception=False,
            set_status_on_exception=False,
            end_on_exit=True,
        ):
            code = response_future.code()
            if code != grpc.StatusCode.OK:
                details = response_future.details()
                span.set_attribute(
                    SpanAttributes.RPC_GRPC_STATUS_CODE, code.value[0]
                )
                span.set_status(
                    Status(
                        status_code=StatusCode.ERROR,
                        description=f"{code}: {details}",
                    )
                )

                try:
                    span.record_exception(response_future.exception())
                except grpc.FutureCancelledError:
                    pass

            else:
                response = response_future.result()
                if response is not None:
                    metric_recorder._record_unary_response(
                        span, response, MessageTypeValues.RECEIVED, attributes
                    )

        metric_recorder._record_duration(
            start_time, attributes, response_future
        )

    return callback


class OpenTelemetryClientInterceptor(
    _EventMetricRecorder,
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
    grpc.StreamUnaryClientInterceptor,
    grpc.StreamStreamClientInterceptor,
):
    def __init__(self, meter, tracer):
        super().__init__(meter, _MetricKind.CLIENT)
        self._tracer = tracer

    def _create_attributes(self, full_method: str) -> Attributes:
        service, method = full_method.lstrip("/").split("/", 1)
        return {
            SpanAttributes.RPC_SYSTEM: RpcSystemValues.GRPC.value,
            SpanAttributes.RPC_SERVICE: service,
            SpanAttributes.RPC_METHOD: method,
            SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[0],
        }

    def intercept_unary_unary(
        self,
        continuation,
        client_call_details: grpc.ClientCallDetails,
        request: ProtoMessage,
    ):
        if context.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return continuation(client_call_details, request)

        attributes = self._create_attributes(client_call_details.method)

        if not client_call_details.metadata:
            mutable_metadata = OrderedDict()
        else:
            mutable_metadata = OrderedDict(client_call_details.metadata)

        with self._tracer.start_as_current_span(
            name=client_call_details.method,
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            response_future = None
            start_time = 0.0

            try:
                inject(mutable_metadata, setter=_carrier_setter)
                metadata = tuple(mutable_metadata.items())
                new_client_call_details = _ClientCallDetails(
                    method=client_call_details.method,
                    timeout=client_call_details.timeout,
                    metadata=metadata,
                    credentials=client_call_details.credentials,
                    wait_for_ready=client_call_details.wait_for_ready,
                    compression=client_call_details.compression,
                )

                start_time = self._start_duration_measurement()
                self._record_unary_request(
                    span, request, MessageTypeValues.SENT, attributes
                )

                response_future = continuation(
                    new_client_call_details, request
                )

            finally:
                if not response_future:
                    span.end()
                else:
                    response_future.add_done_callback(
                        _make_future_done_callback(
                            span, self, attributes, start_time
                        )
                    )

            return response_future

    def intercept_unary_stream(
        self,
        continuation,
        client_call_details: grpc.ClientCallDetails,
        request: ProtoMessage,
    ):
        if context.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return continuation(client_call_details, request)

        attributes = self._create_attributes(client_call_details.method)

        if not client_call_details.metadata:
            mutable_metadata = OrderedDict()
        else:
            mutable_metadata = OrderedDict(client_call_details.metadata)

        with self._tracer.start_as_current_span(
            name=client_call_details.method,
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            inject(mutable_metadata, setter=_carrier_setter)
            metadata = tuple(mutable_metadata.items())
            new_client_call_details = _ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=metadata,
                credentials=client_call_details.credentials,
                wait_for_ready=client_call_details.wait_for_ready,
                compression=client_call_details.compression,
            )

            start_time = self._start_duration_measurement()
            self._record_unary_request(
                span, request, MessageTypeValues.SENT, attributes
            )

            response_iterator = continuation(new_client_call_details, request)

            return _OpentelemetryResponseIterator(
                response_iterator, self, span, attributes, start_time
            )

    def intercept_stream_unary(
        self,
        continuation,
        client_call_details: grpc.ClientCallDetails,
        request_iterator: Iterator[ProtoMessage],
    ):
        if context.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return continuation(client_call_details, request_iterator)

        attributes = self._create_attributes(client_call_details.method)

        if not client_call_details.metadata:
            mutable_metadata = OrderedDict()
        else:
            mutable_metadata = OrderedDict(client_call_details.metadata)

        with self._tracer.start_as_current_span(
            name=client_call_details.method,
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            response_future = None
            start_time = 0

            try:
                inject(mutable_metadata, setter=_carrier_setter)
                metadata = tuple(mutable_metadata.items())
                new_client_call_details = _ClientCallDetails(
                    method=client_call_details.method,
                    timeout=client_call_details.timeout,
                    metadata=metadata,
                    credentials=client_call_details.credentials,
                    wait_for_ready=client_call_details.wait_for_ready,
                    compression=client_call_details.compression,
                )

                start_time = self._start_duration_measurement()
                request_iterator = self._record_streaming_request(
                    span, request_iterator, MessageTypeValues.SENT, attributes
                )

                response_future = continuation(
                    new_client_call_details, request_iterator
                )

            finally:
                if not response_future:
                    span.end()
                else:
                    response_future.add_done_callback(
                        _make_future_done_callback(
                            span, self, attributes, start_time
                        )
                    )

            return response_future

    def intercept_stream_stream(
        self,
        continuation,
        client_call_details: grpc.ClientCallDetails,
        request_iterator: Iterator[ProtoMessage],
    ):
        if context.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return continuation(client_call_details, request_iterator)

        attributes = self._create_attributes(client_call_details.method)

        if not client_call_details.metadata:
            mutable_metadata = OrderedDict()
        else:
            mutable_metadata = OrderedDict(client_call_details.metadata)

        with self._tracer.start_as_current_span(
            name=client_call_details.method,
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            inject(mutable_metadata, setter=_carrier_setter)
            metadata = tuple(mutable_metadata.items())
            new_client_call_details = _ClientCallDetails(
                method=client_call_details.method,
                timeout=client_call_details.timeout,
                metadata=metadata,
                credentials=client_call_details.credentials,
                wait_for_ready=client_call_details.wait_for_ready,
                compression=client_call_details.compression,
            )

            start_time = self._start_duration_measurement()
            request_iterator = self._record_streaming_request(
                span, request_iterator, MessageTypeValues.SENT, attributes
            )

            response_iterator = continuation(
                new_client_call_details, request_iterator
            )

            return _OpentelemetryResponseIterator(
                response_iterator, self, span, attributes, start_time
            )
