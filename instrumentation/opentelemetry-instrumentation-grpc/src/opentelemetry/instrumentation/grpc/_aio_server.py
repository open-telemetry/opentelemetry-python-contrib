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

import grpc
import grpc.aio
import wrapt

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import _report_new
from opentelemetry.instrumentation.grpc._semconv import (
    _apply_grpc_status,
    _apply_server_error,
)

from ._server import OpenTelemetryServerInterceptor, _wrap_rpc_behavior


# pylint:disable=abstract-method
class _OpenTelemetryAioServicerContext(wrapt.ObjectProxy):
    def __init__(self, servicer_context):
        super().__init__(servicer_context)
        self._self_code = None
        self._self_details = None

    async def abort(self, code, details="", trailing_metadata=tuple()):
        self._self_code = code
        self._self_details = details
        return await self.__wrapped__.abort(code, details, trailing_metadata)

    def set_code(self, code):
        self._self_code = code
        return self.__wrapped__.set_code(code)

    def set_details(self, details):
        self._self_details = details
        return self.__wrapped__.set_details(details)


class OpenTelemetryAioServerInterceptor(
    grpc.aio.ServerInterceptor, OpenTelemetryServerInterceptor
):
    """
    An AsyncIO gRPC server interceptor, to add OpenTelemetry.
    Usage::
        tracer = some OpenTelemetry tracer
        interceptors = [
            AsyncOpenTelemetryServerInterceptor(tracer),
        ]
        server = aio.server(
            futures.ThreadPoolExecutor(max_workers=concurrency),
            interceptors = (interceptors,))
    """

    async def intercept_service(self, continuation, handler_call_details):
        if self._filter is not None and not self._filter(handler_call_details):
            return await continuation(handler_call_details)

        def telemetry_wrapper(behavior, request_streaming, response_streaming):
            # handle streaming responses specially
            if response_streaming:
                return self._intercept_aio_server_stream(
                    behavior,
                    handler_call_details,
                )

            return self._intercept_aio_server_unary(
                behavior,
                handler_call_details,
            )

        handler = await continuation(handler_call_details)
        if handler is None:
            if _report_new(self._sem_conv_opt_in_mode):
                async def _unimplemented(_request, context):
                    self._handle_unimplemented(handler_call_details, context)
                # TODO: I still don't like it, figure out how not to
                # change server behavior.
                return grpc.unary_unary_rpc_method_handler(_unimplemented)
            return None
        return _wrap_rpc_behavior(handler, telemetry_wrapper)

    def _intercept_aio_server_unary(self, behavior, handler_call_details):
        async def _unary_interceptor(request_or_iterator, context):
            with self._set_remote_context(context):
                with self._start_span(
                    handler_call_details,
                    context,
                    set_status_on_exception=False,
                ) as span:
                    self._set_peer_attributes(span, context)
                    # wrap the context
                    context = _OpenTelemetryAioServicerContext(
                        context
                    )

                    # And now we run the actual RPC.
                    try:
                        result = await behavior(request_or_iterator, context)
                        _apply_grpc_status(
                            span, context._self_code, trace.SpanKind.SERVER,
                            self._sem_conv_opt_in_mode, context._self_details,
                        )
                        return result

                    except Exception as error:
                        _apply_server_error(
                            span, error, context._self_code, context._self_details,
                            self._sem_conv_opt_in_mode,
                        )
                        raise error

        return _unary_interceptor

    def _intercept_aio_server_stream(self, behavior, handler_call_details):
        async def _stream_interceptor(request_or_iterator, context):
            with self._set_remote_context(context):
                with self._start_span(
                    handler_call_details,
                    context,
                    set_status_on_exception=False,
                ) as span:
                    self._set_peer_attributes(span, context)
                    context = _OpenTelemetryAioServicerContext(
                        context
                    )

                    try:
                        async for response in behavior(
                            request_or_iterator, context
                        ):
                            yield response
                            _apply_grpc_status(
                                span, context._self_code, trace.SpanKind.SERVER,
                                self._sem_conv_opt_in_mode, context._self_details,
                            )

                    except Exception as error:
                        _apply_server_error(
                            span, error, context._self_code, context._self_details,
                            self._sem_conv_opt_in_mode,
                        )
                        raise error

        return _stream_interceptor
