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

"""
Implementation of the service-side open-telemetry interceptor.
"""

import copy
import logging
from contextlib import contextmanager
from typing import Callable, Iterator, Generator, Optional

import grpc

from opentelemetry import metrics, trace
from opentelemetry.context import attach, detach
from opentelemetry.instrumentation.grpc._types import (
    ProtoMessage,
    ProtoMessageOrIterator,
)
from opentelemetry.instrumentation.grpc._utilities import (
    _EventMetricRecorder,
    _MetricKind,
    _OpenTelemetryServicerContext,
)
from opentelemetry.propagate import extract
from opentelemetry.semconv.trace import (
    MessageTypeValues,
    RpcSystemValues,
    SpanAttributes,
)
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util.types import Attributes


logger = logging.getLogger(__name__)


_RPC_USER_AGENT = "rpc.user_agent"
"""span attribute for RPC user agent."""


# wrap an RPC call
# see https://github.com/grpc/grpc/issues/18191
def _wrap_rpc_behavior(
    handler: Optional[grpc.RpcMethodHandler],
    continuation: Callable[
        [ProtoMessageOrIterator, grpc.ServicerContext], ProtoMessageOrIterator
    ],
) -> Optional[grpc.RpcMethodHandler]:
    if handler is None:
        return None

    if handler.request_streaming and handler.response_streaming:
        behavior_fn = handler.stream_stream
        handler_factory = grpc.stream_stream_rpc_method_handler
    elif handler.request_streaming and not handler.response_streaming:
        behavior_fn = handler.stream_unary
        handler_factory = grpc.stream_unary_rpc_method_handler
    elif not handler.request_streaming and handler.response_streaming:
        behavior_fn = handler.unary_stream
        handler_factory = grpc.unary_stream_rpc_method_handler
    else:
        behavior_fn = handler.unary_unary
        handler_factory = grpc.unary_unary_rpc_method_handler

    return handler_factory(
        continuation(
            behavior_fn, handler.request_streaming, handler.response_streaming
        ),
        request_deserializer=handler.request_deserializer,
        response_serializer=handler.response_serializer,
    )


# pylint:disable=abstract-method
# pylint:disable=no-self-use
# pylint:disable=unused-argument
class OpenTelemetryServerInterceptor(
    _EventMetricRecorder, grpc.ServerInterceptor
):
    """
    A gRPC server interceptor, to add OpenTelemetry.

    Usage::

        meter = some OpenTelemetry meter
        tracer = some OpenTelemetry tracer

        interceptors = [
            OpenTelemetryServerInterceptor(meter, tracer),
        ]

        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=concurrency),
            interceptors = interceptors
        )

    """

    def __init__(self, meter: metrics.Meter, tracer: trace.Tracer) -> None:
        super().__init__(meter, _MetricKind.SERVER)
        self._tracer = tracer

    @contextmanager
    def _set_remote_context(
        self, context: grpc.ServicerContext
    ) -> Generator[None, None, None]:
        metadata = context.invocation_metadata()
        if metadata:
            md_dict = {md.key: md.value for md in metadata}
            ctx = extract(md_dict)
            token = attach(ctx)
            try:
                yield
            finally:
                detach(token)
        else:
            yield

    def _create_attributes(
        self, context: grpc.ServicerContext, full_method: str
    ) -> Attributes:
        # standard attributes
        service, method = full_method.lstrip("/").split("/", 1)
        attributes = {
            SpanAttributes.RPC_SYSTEM: RpcSystemValues.GRPC.value,
            SpanAttributes.RPC_SERVICE: service,
            SpanAttributes.RPC_METHOD: method,
        }

        # add some attributes from the metadata
        metadata = dict(context.invocation_metadata())
        if "user-agent" in metadata:
            attributes[_RPC_USER_AGENT] = metadata["user-agent"]

        # Split up the peer to keep with how other telemetry sources
        # do it.  This looks like:
        # * ipv6:[::1]:57284
        # * ipv4:127.0.0.1:57284
        # * ipv4:10.2.1.1:57284,127.0.0.1:57284
        #
        try:
            ip, port = (
                context.peer().split(",")[0].split(":", 1)[1].rsplit(":", 1)
            )
            attributes.update(
                {
                    SpanAttributes.NET_PEER_IP: ip,
                    SpanAttributes.NET_PEER_PORT: port,
                }
            )

            # other telemetry sources add this, so we will too
            if ip in ("[::1]", "127.0.0.1"):
                attributes[SpanAttributes.NET_PEER_NAME] = "localhost"

        except IndexError:
            logger.warning("Failed to parse peer address '%s'", context.peer())

        return attributes

    def intercept_service(
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Optional[grpc.RpcMethodHandler]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> Optional[grpc.RpcMethodHandler]:
        def telemetry_wrapper(
            behavior: Callable[
                [ProtoMessageOrIterator, grpc.ServicerContext],
                ProtoMessageOrIterator,
            ],
            request_streaming: bool,
            response_streaming: bool,
        ) -> Callable[
            [ProtoMessageOrIterator, grpc.ServicerContext],
            ProtoMessageOrIterator,
        ]:
            def telemetry_interceptor(
                request_or_iterator: ProtoMessageOrIterator,
                context: grpc.ServicerContext,
            ) -> ProtoMessageOrIterator:
                if request_streaming and response_streaming:
                    return self.intercept_stream_stream(
                        behavior,
                        request_or_iterator,
                        context,
                        handler_call_details.method,
                    )
                if not request_streaming and response_streaming:
                    return self.intercept_unary_stream(
                        behavior,
                        request_or_iterator,
                        context,
                        handler_call_details.method,
                    )
                if request_streaming and not response_streaming:
                    return self.intercept_stream_unary(
                        behavior,
                        request_or_iterator,
                        context,
                        handler_call_details.method,
                    )
                return self.intercept_unary_unary(
                    behavior,
                    request_or_iterator,
                    context,
                    handler_call_details.method,
                )

            return telemetry_interceptor

        return _wrap_rpc_behavior(
            continuation(handler_call_details), telemetry_wrapper
        )

    def intercept_unary_unary(
        self,
        continuation: Callable[
            [ProtoMessage, grpc.ServicerContext], ProtoMessage
        ],
        request: ProtoMessage,
        context: grpc.ServicerContext,
        full_method: str,
    ) -> ProtoMessage:

        with self._set_remote_context(context):
            metric_attributes = self._create_attributes(context, full_method)
            span_attributes = copy.deepcopy(metric_attributes)
            span_attributes[
                SpanAttributes.RPC_GRPC_STATUS_CODE
            ] = grpc.StatusCode.OK.value[0]

            with self._tracer.start_as_current_span(
                name=full_method,
                kind=trace.SpanKind.SERVER,
                attributes=span_attributes,
                end_on_exit=True,
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                # wrap the context
                context = _OpenTelemetryServicerContext(context, span)

                with self._record_duration_manager(metric_attributes, context):
                    try:
                        # record the request
                        self._record_unary_request(
                            span,
                            request,
                            MessageTypeValues.RECEIVED,
                            metric_attributes,
                        )

                        # call the actual RPC
                        response = continuation(request, context)

                        # record the response
                        self._record_unary_response(
                            span,
                            response,
                            MessageTypeValues.SENT,
                            metric_attributes,
                        )

                        return response

                    except Exception as exc:
                        # Bare exceptions are likely to be gRPC aborts, which
                        # we handle in our context wrapper.
                        # Here, we're interested in uncaught exceptions.
                        # pylint:disable=unidiomatic-typecheck
                        if type(exc) != Exception:
                            span.set_attribute(
                                SpanAttributes.RPC_GRPC_STATUS_CODE,
                                grpc.StatusCode.UNKNOWN.value[0],
                            )
                            span.set_status(
                                Status(
                                    status_code=StatusCode.ERROR,
                                    description=f"{type(exc).__name__}: {exc}",
                                )
                            )
                            span.record_exception(exc)
                        raise exc

    def intercept_unary_stream(
        self,
        continuation: Callable[
            [ProtoMessage, grpc.ServicerContext], Iterator[ProtoMessage]
        ],
        request: ProtoMessage,
        context: grpc.ServicerContext,
        full_method: str,
    ) -> Iterator[ProtoMessage]:

        with self._set_remote_context(context):
            metric_attributes = self._create_attributes(context, full_method)
            span_attributes = copy.deepcopy(metric_attributes)
            span_attributes[
                SpanAttributes.RPC_GRPC_STATUS_CODE
            ] = grpc.StatusCode.OK.value[0]

            with self._tracer.start_as_current_span(
                name=full_method,
                kind=trace.SpanKind.SERVER,
                attributes=span_attributes,
                end_on_exit=True,
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                # wrap the context
                context = _OpenTelemetryServicerContext(context, span)

                with self._record_duration_manager(metric_attributes, context):
                    try:
                        # record the request
                        self._record_unary_request(
                            span,
                            request,
                            MessageTypeValues.RECEIVED,
                            metric_attributes,
                        )

                        # call the actual RPC
                        response_iterator = continuation(request, context)

                        # wrap the response iterator with a recorder
                        yield from self._record_streaming_response(
                            span,
                            response_iterator,
                            MessageTypeValues.SENT,
                            metric_attributes,
                        )

                    except Exception as exc:
                        # Bare exceptions are likely to be gRPC aborts, which
                        # we handle in our context wrapper.
                        # Here, we're interested in uncaught exceptions.
                        # pylint:disable=unidiomatic-typecheck
                        if type(exc) != Exception:
                            span.set_attribute(
                                SpanAttributes.RPC_GRPC_STATUS_CODE,
                                grpc.StatusCode.UNKNOWN.value[0],
                            )
                            span.set_status(
                                Status(
                                    status_code=StatusCode.ERROR,
                                    description=f"{type(exc).__name__}: {exc}",
                                )
                            )
                            span.record_exception(exc)
                        raise exc

    def intercept_stream_unary(
        self,
        continuation: Callable[
            [Iterator[ProtoMessage], grpc.ServicerContext], ProtoMessage
        ],
        request_iterator: Iterator[ProtoMessage],
        context: grpc.ServicerContext,
        full_method: str,
    ) -> ProtoMessage:

        with self._set_remote_context(context):
            metric_attributes = self._create_attributes(context, full_method)
            span_attributes = copy.deepcopy(metric_attributes)
            span_attributes[
                SpanAttributes.RPC_GRPC_STATUS_CODE
            ] = grpc.StatusCode.OK.value[0]

            with self._tracer.start_as_current_span(
                name=full_method,
                kind=trace.SpanKind.SERVER,
                attributes=span_attributes,
                end_on_exit=True,
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                # wrap the context
                context = _OpenTelemetryServicerContext(context, span)

                with self._record_duration_manager(metric_attributes, context):
                    try:
                        # wrap the request iterator with a recorder
                        request_iterator = self._record_streaming_request(
                            span,
                            request_iterator,
                            MessageTypeValues.RECEIVED,
                            metric_attributes,
                        )

                        # call the actual RPC
                        response = continuation(request_iterator, context)

                        # record the response
                        self._record_unary_response(
                            span,
                            response,
                            MessageTypeValues.SENT,
                            metric_attributes,
                        )

                        return response

                    except Exception as exc:
                        # Bare exceptions are likely to be gRPC aborts, which
                        # we handle in our context wrapper.
                        # Here, we're interested in uncaught exceptions.
                        # pylint:disable=unidiomatic-typecheck
                        if type(exc) != Exception:
                            span.set_attribute(
                                SpanAttributes.RPC_GRPC_STATUS_CODE,
                                grpc.StatusCode.UNKNOWN.value[0],
                            )
                            span.set_status(
                                Status(
                                    status_code=StatusCode.ERROR,
                                    description=f"{type(exc).__name__}: {exc}",
                                )
                            )
                            span.record_exception(exc)
                        raise exc

    def intercept_stream_stream(
        self,
        continuation: Callable[
            [Iterator[ProtoMessage], grpc.ServicerContext],
            Iterator[ProtoMessage],
        ],
        request_iterator: Iterator[ProtoMessage],
        context: grpc.ServicerContext,
        full_method: str,
    ) -> Iterator[ProtoMessage]:

        with self._set_remote_context(context):
            metric_attributes = self._create_attributes(context, full_method)
            span_attributes = copy.deepcopy(metric_attributes)
            span_attributes[
                SpanAttributes.RPC_GRPC_STATUS_CODE
            ] = grpc.StatusCode.OK.value[0]

            with self._tracer.start_as_current_span(
                name=full_method,
                kind=trace.SpanKind.SERVER,
                attributes=span_attributes,
                end_on_exit=True,
                record_exception=False,
                set_status_on_exception=False,
            ) as span:
                # wrap the context
                context = _OpenTelemetryServicerContext(context, span)

                with self._record_duration_manager(metric_attributes, context):
                    try:
                        # wrap the request iterator with a recorder
                        request_iterator = self._record_streaming_request(
                            span,
                            request_iterator,
                            MessageTypeValues.RECEIVED,
                            metric_attributes,
                        )

                        # call the actual RPC
                        response_iterator = continuation(
                            request_iterator, context
                        )

                        # wrap the response iterator with a recorder
                        yield from self._record_streaming_response(
                            span,
                            response_iterator,
                            MessageTypeValues.SENT,
                            metric_attributes,
                        )

                    except Exception as exc:
                        # Bare exceptions are likely to be gRPC aborts, which
                        # we handle in our context wrapper.
                        # Here, we're interested in uncaught exceptions.
                        # pylint:disable=unidiomatic-typecheck
                        if type(exc) != Exception:
                            span.set_attribute(
                                SpanAttributes.RPC_GRPC_STATUS_CODE,
                                grpc.StatusCode.UNKNOWN.value[0],
                            )
                            span.set_status(
                                Status(
                                    status_code=StatusCode.ERROR,
                                    description=f"{type(exc).__name__}: {exc}",
                                )
                            )
                            span.record_exception(exc)
                        raise exc
