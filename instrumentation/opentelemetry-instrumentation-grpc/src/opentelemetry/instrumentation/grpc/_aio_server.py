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

from ._server import (
    OpenTelemetryServerInterceptor,
    _wrap_rpc_behavior,
)

from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.status import Status, StatusCode

# pylint:disable=abstract-method
class _OpenTelemetryAioServicerContext(grpc.aio.ServicerContext):
    def __init__(self, servicer_context, active_span):
        self._servicer_context = servicer_context
        self._active_span = active_span
        self._code = grpc.StatusCode.OK
        self._details = None
        super().__init__()

    def __getattr__(self, attr):
        return getattr(self._servicer_context, attr)

    async def read(self):
        return await self._servicer_context.read()

    async def write(self, message):
        return await self._servicer_context.write(message)

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

    async def send_initial_metadata(self, *args, **kwargs):
        return await self._servicer_context.send_initial_metadata(*args, **kwargs)

    def set_trailing_metadata(self, *args, **kwargs):
        return self._servicer_context.set_trailing_metadata(*args, **kwargs)

    def trailing_metadata(self):
        return self._servicer_context.trailing_metadata()

    async def abort(self, code, details = "", trailing_metadata = tuple()):
        self._code = code
        self._details = details
        self._active_span.set_attribute(
            SpanAttributes.RPC_GRPC_STATUS_CODE, code.value[0]
        )
        self._active_span.set_status(
            Status(
                status_code=StatusCode.ERROR,
                description=f"{code}:{details}",
            )
        )
        return await self._servicer_context.abort(code, details, trailing_metadata)

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
        # use details if we already have it, otherwise the status description
        details = self._details or code.value[1]
        self._active_span.set_attribute(
            SpanAttributes.RPC_GRPC_STATUS_CODE, code.value[0]
        )
        if code != grpc.StatusCode.OK:
            self._active_span.set_status(
                Status(
                    status_code=StatusCode.ERROR,
                    description=f"{code}:{details}",
                )
            )
        return self._servicer_context.set_code(code)

    def set_details(self, details):
        self._details = details
        if self._code != grpc.StatusCode.OK:
            self._active_span.set_status(
                Status(
                    status_code=StatusCode.ERROR,
                    description=f"{self._code}:{details}",
                )
            )
        return self._servicer_context.set_details(details)


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

        next_handler = await continuation(handler_call_details)

        return _wrap_rpc_behavior(next_handler, telemetry_wrapper)

    def _intercept_aio_server_unary(self, behavior, handler_call_details):
        async def _unary_interceptor(request_or_iterator, context):
            with self._set_remote_context(context):
                with self._start_span(
                    handler_call_details,
                    context,
                    set_status_on_exception=False,
                ) as span:
                    # wrap the context
                    context = _OpenTelemetryAioServicerContext(context, span)

                    # And now we run the actual RPC.
                    try:
                        return await behavior(request_or_iterator, context)

                    except Exception as error:
                        # Bare exceptions are likely to be gRPC aborts, which
                        # we handle in our context wrapper.
                        # Here, we're interested in uncaught exceptions.
                        # pylint:disable=unidiomatic-typecheck
                        if type(error) != Exception:
                            span.record_exception(error)
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
                    context = _OpenTelemetryAioServicerContext(context, span)

                    try:
                        async for response in behavior(
                            request_or_iterator, context
                        ):
                            yield response

                    except Exception as error:
                        # pylint:disable=unidiomatic-typecheck
                        if type(error) != Exception:
                            span.record_exception(error)
                        raise error

        return _stream_interceptor
