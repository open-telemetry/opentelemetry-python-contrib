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

import logging
from contextlib import contextmanager

import grpc

from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.propagate import extract
from opentelemetry.semconv.trace import MessageTypeValues, RpcSystemValues, SpanAttributes
from opentelemetry.trace.status import Status, StatusCode
from opentelemetry.util._time import _time_ns


logger = logging.getLogger(__name__)


_MESSAGE = "message"
"""event name of a message."""

_RPC_USER_AGENT = "rpc.user_agent"
"""span attribute for RPC user agent."""


# wrap an RPC call
# see https://github.com/grpc/grpc/issues/18191
def _wrap_rpc_behavior(handler, continuation):
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


def _add_message_event(
    span,
    message_type,
    message_size_by,
    message_id=1
):
    span.add_event(
        _MESSAGE,
        {
            SpanAttributes.MESSAGE_TYPE: message_type,
            SpanAttributes.MESSAGE_ID: message_id,
            SpanAttributes.MESSAGE_UNCOMPRESSED_SIZE: message_size_by,
        }
    )


# pylint:disable=abstract-method
class _OpenTelemetryServicerContext(grpc.ServicerContext):

    def __init__(self, servicer_context, active_span):
        self._servicer_context = servicer_context
        self._active_span = active_span
        self._code = grpc.StatusCode.OK
        self._details = None
        super().__init__()

    def __getattr__(self, attr):
        return getattr(self._servicer_context, attr)

    def is_active(self, *args, **kwargs):
        return self._servicer_context.is_active(*args, **kwargs)

    def time_remaining(self, *args, **kwargs):
        return self._servicer_context.time_remaining(*args, **kwargs)

    def cancel(self, *args, **kwargs):
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
        return self._servicer_context.cancel(*args, **kwargs)

    def add_callback(self, *args, **kwargs):
        return self._servicer_context.add_callback(*args, **kwargs)

    def disable_next_message_compression(self):
        return self._service_context.disable_next_message_compression()

    def invocation_metadata(self):
        return self._servicer_context.invocation_metadata()

    def peer(self):
        return self._servicer_context.peer()

    def peer_identities(self):
        return self._servicer_context.peer_identities()

    def peer_identity_key(self):
        return self._servicer_context.peer_identity_key()

    def auth_context(self):
        return self._servicer_context.auth_context()

    def set_compression(self, compression):
        return self._servicer_context.set_compression(compression)

    def send_initial_metadata(self, *args, **kwargs):
        return self._servicer_context.send_initial_metadata(*args, **kwargs)

    def set_trailing_metadata(self, *args, **kwargs):
        return self._servicer_context.set_trailing_metadata(*args, **kwargs)

    def trailing_metadata(self):
        return self._servicer_context.trailing_metadata()

    def abort(self, code, details):
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

    def abort_with_status(self, status):
        if not hasattr(self._servicer_context, "abort_with_status"):
            raise RuntimeError(
                "abort_with_status() is not supported with the installed version of grpcio"
            )
        return self._servicer_context.abort_with_status(status)

    def code(self):
        if not hasattr(self._servicer_context, "code"):
            raise RuntimeError(
                "code() is not supported with the installed version of grpcio"
            )
        return self._servicer_context.code()

    def set_code(self, code):
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

    def details(self):
        if not hasattr(self._servicer_context, "details"):
            raise RuntimeError(
                "details() is not supported with the installed version of "
                "grpcio"
            )
        return self._servicer_context.details()

    def set_details(self, details):
        self._details = details
        if self._code != grpc.StatusCode.OK:
            self._active_span.set_status(
                Status(
                    status_code=StatusCode.ERROR,
                    description=f"{self._code}: {details}",
                )
            )
        return self._servicer_context.set_details(details)


# pylint:disable=abstract-method
# pylint:disable=no-self-use
# pylint:disable=unused-argument
class OpenTelemetryServerInterceptor(grpc.ServerInterceptor):
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

    def __init__(self, meter, tracer):
        self._meter = meter
        self._tracer = tracer

        self._duration_histogram = self._meter.create_histogram(
            name="rpc.server.duration",
            unit="ms",
            description="measures the duration of the inbound rpc",
        )
        self._request_size_histogram = self._meter.create_histogram(
            name="rpc.server.request.size",
            unit="By",
            description="measures size of RPC request messages (uncompressed)",
        )
        self._response_size_histogram = self._meter.create_histogram(
            name="rpc.server.response.size",
            unit="By",
            description="measures size of RPC response messages (uncompressed)",
        )
        self._requests_per_rpc_histogram = self._meter.create_histogram(
            name="rpc.server.requests_per_rpc",
            unit="requests",
            description="measures the number of messages received per RPC. Should be 1 for all non-streaming RPCs",
        )
        self._responses_per_rpc_histogram = self._meter.create_histogram(
            name="rpc.server.responses_per_rpc",
            unit="responses",
            description="measures the number of messages sent per RPC. Should be 1 for all non-streaming RPCs",
        )

    @contextmanager
    def _set_remote_context(self, context):
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

    def _create_attributes(self, context, full_method):
        # standard attributes
        attributes = {
            SpanAttributes.RPC_SYSTEM: RpcSystemValues.GRPC.value,
            SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[0],
        }

        # add service and method attributes
        service, method = full_method.lstrip("/").split("/", 1)
        attributes.update(
            {
                SpanAttributes.RPC_SERVICE: service,
                SpanAttributes.RPC_METHOD: method,
            }
        )

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

    def intercept_service(self, continuation, handler_call_details):
        def telemetry_wrapper(behavior, request_streaming, response_streaming):
            def telemetry_interceptor(request_or_iterator, context):
                with self._set_remote_context(context):
                    attributes = self._create_attributes(context, handler_call_details.method)

                    with self._tracer.start_as_current_span(
                        name=handler_call_details.method,
                        kind=trace.SpanKind.SERVER,
                        attributes=attributes,
                        end_on_exit=False,
                        record_exception=False,
                        set_status_on_exception=False
                    ) as span:

                        try:
                            # wrap the context
                            context = _OpenTelemetryServicerContext(context, span)

                            # wrap / log the request (iterator)
                            if request_streaming:
                                request_or_iterator = self._log_stream_requests(
                                    request_or_iterator, span, attributes
                                )
                            else:
                                self._log_unary_request(
                                    request_or_iterator, span, attributes
                                )

                            # call the actual RPC and track the duration
                            with self._record_duration(attributes, context):
                                response_or_iterator = behavior(request_or_iterator, context)

                            # wrap / log the response (iterator)
                            if response_streaming:
                                response_or_iterator = self._log_stream_responses(
                                    response_or_iterator, span, attributes, context
                                )
                            else:
                                self._log_unary_response(
                                    response_or_iterator, span, attributes, context
                                )

                            return response_or_iterator

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

                        finally:
                            if not response_streaming:
                                span.end()

            return telemetry_interceptor

        return _wrap_rpc_behavior(
            continuation(handler_call_details),
            telemetry_wrapper
        )

    def _log_unary_request(self, request, active_span, attributes):
        message_size_by = request.ByteSize()
        _add_message_event(
            active_span, MessageTypeValues.RECEIVED.value, message_size_by
        )
        self._request_size_histogram.record(message_size_by, attributes)
        self._requests_per_rpc_histogram.record(1, attributes)

    def _log_unary_response(self, response, active_span, attributes, context):
        message_size_by = response.ByteSize()
        _add_message_event(
            active_span, MessageTypeValues.SENT.value, message_size_by
        )
        if context._code != grpc.StatusCode.OK:
            attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = context._code.value[0]
        self._response_size_histogram.record(message_size_by, attributes)
        self._responses_per_rpc_histogram.record(1, attributes)

    def _log_stream_requests(self, request_iterator, active_span, attributes):
        req_id = 1
        for req_id, msg in enumerate(request_iterator, start=1):
            message_size_by = msg.ByteSize()
            _add_message_event(
                active_span, MessageTypeValues.RECEIVED.value, message_size_by, message_id=req_id
            )
            self._request_size_histogram.record(message_size_by, attributes)
            yield msg

        self._requests_per_rpc_histogram.record(req_id, attributes)

    def _log_stream_responses(self, response_iterator, active_span, attributes, context):
        with trace.use_span(
            active_span,
            end_on_exit=True,
            record_exception=False,
            set_status_on_exception=False
        ):
            try:
                res_id = 1
                for res_id, msg in enumerate(response_iterator, start=1):
                    message_size_by = msg.ByteSize()
                    _add_message_event(
                        active_span, MessageTypeValues.SENT.value, message_size_by, message_id=res_id
                    )
                    self._response_size_histogram.record(message_size_by, attributes)
                    yield msg
            except Exception as exc:
                # Bare exceptions are likely to be gRPC aborts, which
                # we handle in our context wrapper.
                # Here, we're interested in uncaught exceptions.
                # pylint:disable=unidiomatic-typecheck
                if type(exc) != Exception:
                    active_span.set_attribute(
                        SpanAttributes.RPC_GRPC_STATUS_CODE,
                        grpc.StatusCode.UNKNOWN.value[0]
                    )
                    active_span.set_status(
                        Status(
                            status_code=StatusCode.ERROR,
                            description=f"{type(exc).__name__}: {exc}",
                        )
                    )
                    active_span.record_exception(exc)
                raise exc
            finally:
                if context._code != grpc.StatusCode.OK:
                    attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = context._code.value[0]
                self._responses_per_rpc_histogram.record(res_id, attributes)

    @contextmanager
    def _record_duration(self, attributes, context):
        start = _time_ns()
        try:
            yield
        finally:
            duration = max(round((_time_ns() - start) * 1000), 0)
            if context._code != grpc.StatusCode.OK:
                attributes[SpanAttributes.RPC_GRPC_STATUS_CODE] = context._code.value[0]
            self._duration_histogram.record(duration, attributes)
