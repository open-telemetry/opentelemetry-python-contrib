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
from typing import Callable, Dict, Iterable, Iterator, Generator, NoReturn, Optional

import grpc

from opentelemetry import metrics, trace
from opentelemetry.context import attach, detach
from opentelemetry.instrumentation.grpc._types import Metadata, ProtoMessage, ProtoMessageOrIterator
from opentelemetry.instrumentation.grpc._utilities import _EventMetricRecorder, _MetricKind
from opentelemetry.propagate import extract
from opentelemetry.semconv.trace import MessageTypeValues, RpcSystemValues, SpanAttributes
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
        [ProtoMessageOrIterator, grpc.ServicerContext],
        ProtoMessageOrIterator
    ]
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

    # pylint: disable=invalid-name
    def add_callback(self, fn: Callable[[], None]) -> None:
        return self._servicer_context.add_callback(fn)

    def cancel(self) -> None:
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


# pylint:disable=abstract-method
# pylint:disable=no-self-use
# pylint:disable=unused-argument
class OpenTelemetryServerInterceptor(
    _EventMetricRecorder,
    grpc.ServerInterceptor
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

    def __init__(
        self,
        meter: metrics.Meter,
        tracer: trace.Tracer
    ) -> None:
        super().__init__(meter, _MetricKind.SERVER)
        self._tracer = tracer

    @contextmanager
    def _set_remote_context(
        self,
        context: grpc.ServicerContext
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
        self,
        context: grpc.ServicerContext,
        full_method: str
    ) -> Attributes:
        # standard attributes
        service, method = full_method.lstrip("/").split("/", 1)
        attributes = {
            SpanAttributes.RPC_SYSTEM: RpcSystemValues.GRPC.value,
            SpanAttributes.RPC_SERVICE: service,
            SpanAttributes.RPC_METHOD: method
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
        handler_call_details: grpc.HandlerCallDetails
    ) -> Optional[grpc.RpcMethodHandler]:

        def telemetry_wrapper(
            behavior: Callable[
                [ProtoMessageOrIterator, grpc.ServicerContext],
                ProtoMessageOrIterator
            ],
            request_streaming: bool,
            response_streaming: bool
        ) -> Callable[
            [ProtoMessageOrIterator, grpc.ServicerContext],
            ProtoMessageOrIterator
        ]:

            def telemetry_interceptor(
                request_or_iterator: ProtoMessageOrIterator,
                context: grpc.ServicerContext
            ) -> ProtoMessageOrIterator:
                if request_streaming and response_streaming:
                    return self.intercept_stream_stream(
                        behavior, request_or_iterator, context,
                        handler_call_details.method
                    )
                if not request_streaming and response_streaming:
                    return self.intercept_unary_stream(
                        behavior, request_or_iterator, context,
                        handler_call_details.method
                    )
                if request_streaming and not response_streaming:
                    return self.intercept_stream_unary(
                        behavior, request_or_iterator, context,
                        handler_call_details.method
                    )
                return self.intercept_unary_unary(
                    behavior, request_or_iterator, context,
                    handler_call_details.method
                )

            return telemetry_interceptor

        return _wrap_rpc_behavior(
            continuation(handler_call_details),
            telemetry_wrapper
        )

    def intercept_unary_unary(
        self,
        continuation: Callable[
            [ProtoMessage, grpc.ServicerContext], ProtoMessage
        ],
        request: ProtoMessage,
        context: grpc.ServicerContext,
        full_method: str
    ) -> ProtoMessage:
        with self._set_remote_context(context):
            metric_attributes = self._create_attributes(context, full_method)
            span_attributes = copy.deepcopy(metric_attributes)
            span_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = (
                grpc.StatusCode.OK.value[0]
            )

            with self._tracer.start_as_current_span(
                name=full_method,
                kind=trace.SpanKind.SERVER,
                attributes=span_attributes,
                end_on_exit=True,
                record_exception=False,
                set_status_on_exception=False
            ) as span:
                with self._record_duration_manager(metric_attributes, context):

                    try:
                        # wrap the context
                        context = _OpenTelemetryServicerContext(context, span)

                        # record the request
                        self._record_unary_request(
                            span,
                            request,
                            MessageTypeValues.RECEIVED,
                            metric_attributes
                        )

                        # call the actual RPC
                        response = continuation(request, context)

                        # record the response
                        self._record_unary_response(
                            span,
                            response,
                            MessageTypeValues.SENT,
                            metric_attributes
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
                                grpc.StatusCode.UNKNOWN.value[0]
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
        full_method: str
    ) -> Iterator[ProtoMessage]:
        with self._set_remote_context(context):
            metric_attributes = self._create_attributes(context, full_method)
            span_attributes = copy.deepcopy(metric_attributes)
            span_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = (
                grpc.StatusCode.OK.value[0]
            )

            with self._tracer.start_as_current_span(
                name=full_method,
                kind=trace.SpanKind.SERVER,
                attributes=span_attributes,
                end_on_exit=True,
                record_exception=False,
                set_status_on_exception=False
            ) as span:

                with self._record_duration_manager(metric_attributes, context):
                    try:
                        # wrap the context
                        context = _OpenTelemetryServicerContext(context, span)

                        # record the request
                        self._record_unary_request(
                            span,
                            request,
                            MessageTypeValues.RECEIVED,
                            metric_attributes
                        )

                        # call the actual RPC
                        response_iterator = continuation(request, context)

                        # wrap the response iterator with a recorder
                        yield from self._record_streaming_response(
                            span,
                            response_iterator,
                            MessageTypeValues.SENT,
                            metric_attributes
                        )

                    except Exception as exc:
                        # Bare exceptions are likely to be gRPC aborts, which
                        # we handle in our context wrapper.
                        # Here, we're interested in uncaught exceptions.
                        # pylint:disable=unidiomatic-typecheck
                        if type(exc) != Exception:
                            span.set_attribute(
                                SpanAttributes.RPC_GRPC_STATUS_CODE,
                                grpc.StatusCode.UNKNOWN.value[0]
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
        full_method: str
    ) -> ProtoMessage:
        with self._set_remote_context(context):
            metric_attributes = self._create_attributes(context, full_method)
            span_attributes = copy.deepcopy(metric_attributes)
            span_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = (
                grpc.StatusCode.OK.value[0]
            )

            with self._tracer.start_as_current_span(
                name=full_method,
                kind=trace.SpanKind.SERVER,
                attributes=span_attributes,
                end_on_exit=True,
                record_exception=False,
                set_status_on_exception=False
            ) as span:
                with self._record_duration_manager(metric_attributes, context):

                    try:
                        # wrap the context
                        context = _OpenTelemetryServicerContext(context, span)

                        # wrap the request iterator with a recorder
                        request_iterator = self._record_streaming_request(
                            span,
                            request_iterator,
                            MessageTypeValues.RECEIVED,
                            metric_attributes
                        )

                        # call the actual RPC
                        response = continuation(request_iterator, context)

                        # record the response
                        self._record_unary_response(
                            span,
                            response,
                            MessageTypeValues.SENT,
                            metric_attributes
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
                                grpc.StatusCode.UNKNOWN.value[0]
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
            Iterator[ProtoMessage]
        ],
        request_iterator: Iterator[ProtoMessage],
        context: grpc.ServicerContext,
        full_method: str
    ) -> Iterator[ProtoMessage]:
        with self._set_remote_context(context):
            metric_attributes = self._create_attributes(context, full_method)
            span_attributes = copy.deepcopy(metric_attributes)
            span_attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = (
                grpc.StatusCode.OK.value[0]
            )

            with self._tracer.start_as_current_span(
                name=full_method,
                kind=trace.SpanKind.SERVER,
                attributes=span_attributes,
                end_on_exit=True,
                record_exception=False,
                set_status_on_exception=False
            ) as span:

                with self._record_duration_manager(metric_attributes, context):
                    try:
                        # wrap the context
                        context = _OpenTelemetryServicerContext(context, span)

                        # wrap the request iterator with a recorder
                        request_iterator = self._record_streaming_request(
                            span,
                            request_iterator,
                            MessageTypeValues.RECEIVED,
                            metric_attributes
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
                            metric_attributes
                        )

                    except Exception as exc:
                        # Bare exceptions are likely to be gRPC aborts, which
                        # we handle in our context wrapper.
                        # Here, we're interested in uncaught exceptions.
                        # pylint:disable=unidiomatic-typecheck
                        if type(exc) != Exception:
                            span.set_attribute(
                                SpanAttributes.RPC_GRPC_STATUS_CODE,
                                grpc.StatusCode.UNKNOWN.value[0]
                            )
                            span.set_status(
                                Status(
                                    status_code=StatusCode.ERROR,
                                    description=f"{type(exc).__name__}: {exc}",
                                )
                            )
                            span.record_exception(exc)
                        raise exc
