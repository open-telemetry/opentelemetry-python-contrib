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
from urllib.parse import unquote

import grpc

from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.instrumentation._semconv import (
    _StabilityMode,
    _report_old,
    _report_new,
)
from opentelemetry.instrumentation.grpc._semconv import (
    RPC_METHOD_ORIGINAL,
    _apply_grpc_status,
    _apply_server_error,
    _set_rpc_method,
    _set_rpc_peer_ip_server,
    _set_rpc_peer_name_server,
    _set_rpc_peer_port_server,
    _set_rpc_system,
)
from opentelemetry.propagate import extract

logger = logging.getLogger(__name__)


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


# pylint:disable=abstract-method
class _OpenTelemetryServicerContext(grpc.ServicerContext):
    def __init__(self, servicer_context):
        self._servicer_context = servicer_context
        self._code = None
        self._details = None
        super().__init__()

    def __getattr__(self, attr):
        return getattr(self._servicer_context, attr)

    def is_active(self, *args, **kwargs):
        return self._servicer_context.is_active(*args, **kwargs)

    def time_remaining(self, *args, **kwargs):
        return self._servicer_context.time_remaining(*args, **kwargs)

    def cancel(self, *args, **kwargs):
        return self._servicer_context.cancel(*args, **kwargs)

    def add_callback(self, *args, **kwargs):
        return self._servicer_context.add_callback(*args, **kwargs)

    def disable_next_message_compression(self):
        return self._service_context.disable_next_message_compression()

    def invocation_metadata(self, *args, **kwargs):
        return self._servicer_context.invocation_metadata(*args, **kwargs)

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
        self._code = code
        self._details = details
        return self._servicer_context.abort(code, details)

    def abort_with_status(self, status):
        self._code = status.code
        self._details = status.details
        return self._servicer_context.abort_with_status(status)

    def code(self):
        if not hasattr(self._servicer_context, "code"):
            raise RuntimeError(
                "code() is not supported with the installed version of grpcio"
            )
        return self._servicer_context.code()

    def details(self):
        if not hasattr(self._servicer_context, "details"):
            raise RuntimeError(
                "details() is not supported with the installed version of "
                "grpcio"
            )
        return self._servicer_context.details()

    def set_code(self, code):
        self._code = code
        return self._servicer_context.set_code(code)

    def set_details(self, details):
        self._details = details
        return self._servicer_context.set_details(details)


# pylint:disable=abstract-method
# pylint:disable=no-self-use
# pylint:disable=unused-argument
class OpenTelemetryServerInterceptor(grpc.ServerInterceptor):
    """
    A gRPC server interceptor, to add OpenTelemetry.

    Usage::

        tracer = some OpenTelemetry tracer
        filter = filters.negate(filters.method_name("service.Foo"))

        interceptors = [
            OpenTelemetryServerInterceptor(tracer, filter),
        ]

        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=concurrency),
            interceptors = interceptors)

    """

    def __init__(
        self,
        tracer,
        filter_=None,
        sem_conv_opt_in_mode=_StabilityMode.DEFAULT,
    ):
        self._tracer = tracer
        self._filter = filter_
        self._sem_conv_opt_in_mode = sem_conv_opt_in_mode

    @contextmanager
    def _set_remote_context(self, servicer_context):
        metadata = servicer_context.invocation_metadata()
        if metadata:
            md_dict = {md.key: md.value for md in metadata}
            ctx = extract(md_dict)
            token = attach(ctx)
            try:
                yield
            finally:
                if token:
                    detach(token)
        else:
            yield

    def _start_span(
        self, handler_call_details, context, set_status_on_exception=False
    ):
        attributes = {}

        _set_rpc_system(attributes, "grpc", self._sem_conv_opt_in_mode)

        if handler_call_details.method:
            _set_rpc_method(
                attributes,
                handler_call_details.method,
                self._sem_conv_opt_in_mode,
            )

        if _report_old(self._sem_conv_opt_in_mode):
            # add some attributes from the metadata
            metadata = dict(context.invocation_metadata())
            if "user-agent" in metadata:
                attributes["rpc.user_agent"] = metadata["user-agent"]

        return self._tracer.start_as_current_span(
            name=handler_call_details.method,
            kind=trace.SpanKind.SERVER,
            attributes=attributes,
            set_status_on_exception=set_status_on_exception,
        )

    def _handle_unimplemented(self, handler_call_details, context):
        with self._set_remote_context(context):
            attributes = {}
            _set_rpc_system(attributes, "grpc", self._sem_conv_opt_in_mode)
            attributes["rpc.method"] = "_OTHER"
            if handler_call_details.method:
                attributes[RPC_METHOD_ORIGINAL] = handler_call_details.method
            with self._tracer.start_as_current_span(
                name="_OTHER",
                kind=trace.SpanKind.SERVER,
                attributes=attributes,
            ) as span:
                self._set_peer_attributes(span, context)
                _apply_grpc_status(
                    span,
                    grpc.StatusCode.UNIMPLEMENTED,
                    trace.SpanKind.SERVER,
                    self._sem_conv_opt_in_mode,
                )
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)

    def _set_peer_attributes(self, span, context):
        # Split up the peer to keep with how other telemetry sources
        # do it.  This looks like:
        # * ipv6:[::1]:57284
        # * ipv4:127.0.0.1:57284
        # * ipv4:10.2.1.1:57284,127.0.0.1:57284
        if not span.is_recording():
            return
        peer = context.peer()
        if peer.startswith("unix:"):
            return
        try:
            ip, port = peer.split(",")[0].split(":", 1)[1].rsplit(":", 1)
            ip = unquote(ip)
            attrs = {}
            _set_rpc_peer_ip_server(attrs, ip, self._sem_conv_opt_in_mode)
            _set_rpc_peer_port_server(attrs, port, self._sem_conv_opt_in_mode)
            if ip in ("[::1]", "127.0.0.1"):
                _set_rpc_peer_name_server(attrs, "localhost", self._sem_conv_opt_in_mode)
            for k, v in attrs.items():
                span.set_attribute(k, v)
        except IndexError:
            logger.warning("Failed to parse peer address '%s'", peer)

    def intercept_service(self, continuation, handler_call_details):
        if self._filter is not None and not self._filter(handler_call_details):
            return continuation(handler_call_details)

        def telemetry_wrapper(behavior, request_streaming, response_streaming):
            def telemetry_interceptor(request_or_iterator, context):
                # handle streaming responses specially
                if response_streaming:
                    return self._intercept_server_stream(
                        behavior,
                        handler_call_details,
                        request_or_iterator,
                        context,
                    )

                with self._set_remote_context(context):
                    with self._start_span(
                        handler_call_details,
                        context,
                        set_status_on_exception=False,
                    ) as span:
                        self._set_peer_attributes(span, context)
                        # wrap the context
                        context = _OpenTelemetryServicerContext(
                            context
                        )

                        # And now we run the actual RPC.
                        try:
                            result = behavior(request_or_iterator, context)
                            _apply_grpc_status(
                                    span, context._code, trace.SpanKind.SERVER,
                                    self._sem_conv_opt_in_mode, context._details,
                                )
                            return result
                        except Exception as error:
                            _apply_server_error(
                                span, error, context._code, context._details,
                                self._sem_conv_opt_in_mode,
                            )
                            raise error

            return telemetry_interceptor

        handler = continuation(handler_call_details)
        if handler is None:
            if _report_new(self._sem_conv_opt_in_mode):
                def _unimplemented(_request, context):
                    self._handle_unimplemented(handler_call_details, context)
                return grpc.unary_unary_rpc_method_handler(_unimplemented)
            return None
        return _wrap_rpc_behavior(handler, telemetry_wrapper)

    # Handle streaming responses separately - we have to do this
    # to return a *new* generator or various upstream things
    # get confused, or we'll lose the consistent trace
    def _intercept_server_stream(
        self, behavior, handler_call_details, request_or_iterator, context
    ):
        with self._set_remote_context(context):
            with self._start_span(
                handler_call_details, context, set_status_on_exception=False
            ) as span:
                self._set_peer_attributes(span, context)
                context = _OpenTelemetryServicerContext(
                    context
                )

                try:
                    yield from behavior(request_or_iterator, context)
                    _apply_grpc_status(
                        span, context._code, trace.SpanKind.SERVER,
                        self._sem_conv_opt_in_mode, context._details,
                    )
                except Exception as error:
                    _apply_server_error(
                        span, error, context._code, context._details,
                        self._sem_conv_opt_in_mode,
                    )
                    raise error

