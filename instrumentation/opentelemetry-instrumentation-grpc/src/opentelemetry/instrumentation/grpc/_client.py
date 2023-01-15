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
import functools
from typing import MutableMapping

import grpc
from grpc._interceptor import _ClientCallDetails

from opentelemetry import context, trace
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY
from opentelemetry.propagate import inject
from opentelemetry.propagators.textmap import Setter
from opentelemetry.semconv.trace import RpcSystemValues, SpanAttributes
from opentelemetry.trace.status import Status, StatusCode


class _CarrierSetter(Setter):
    """We use a custom setter in order to be able to lower case
    keys as is required by grpc.
    """

    def set(self, carrier: MutableMapping[str, str], key: str, value: str):
        carrier[key.lower()] = value


_carrier_setter = _CarrierSetter()


def _unary_done_callback(span):
    def callback(response_future):
        with trace.use_span(span, end_on_exit=True):
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

    return callback


class _BaseClientInterceptor:

    def __init__(self, tracer, filter_=None):
        self._tracer = tracer
        self._filter = filter_

    @staticmethod
    def propagate_trace_in_details(client_call_details):
        """Propagates """
        metadata = client_call_details.metadata
        if not metadata:
            mutable_metadata = OrderedDict()
        else:
            mutable_metadata = OrderedDict(metadata)

        inject(mutable_metadata, setter=_carrier_setter)
        metadata = tuple(mutable_metadata.items())

        return _ClientCallDetails(
            client_call_details.method,
            client_call_details.timeout,
            metadata,
            # credentials, wait_for_ready, compression
            *client_call_details[3:]
        )

    @staticmethod
    def add_error_details_to_span(
        span: trace.Span,
        exc: Exception,
    ) -> None:
        """Adds error and details to an active span.

        Args:
            span: The active span.
            exc: The exception to get code and details from.
        """
        if isinstance(exc, grpc.RpcError):
            span.set_attribute(
                SpanAttributes.RPC_GRPC_STATUS_CODE,
                exc.code().value[0],
            )
        span.set_status(
            Status(
                status_code=StatusCode.ERROR,
                description=f"{type(exc).__name__}: {exc}",
            )
        )
        span.record_exception(exc)

    def _start_span(self, method, **kwargs):
        service, meth = method.lstrip("/").split("/", 1)
        attributes = {
            SpanAttributes.RPC_SYSTEM: RpcSystemValues.GRPC.value,
            SpanAttributes.RPC_SERVICE: service,
            SpanAttributes.RPC_METHOD: meth,
            SpanAttributes.RPC_GRPC_STATUS_CODE: grpc.StatusCode.OK.value[0],
        }

        return self._tracer.start_as_current_span(
            name=method,
            kind=trace.SpanKind.CLIENT,
            attributes=attributes,
            **kwargs,
        )

    def _wrap_unary_response(self, span, continuation):
        response_future = None
        try:
            response_future = continuation()
        except Exception as exc:
            self.add_error_details_to_span(span, exc)
            raise exc
        finally:
            if not response_future:
                span.end()

        # If the RPC is called asynchronously, add a callback to end the span
        # when the future is done, else end the span immediately
        if isinstance( response_future, grpc.Future):
            response_future.add_done_callback(_unary_done_callback(span))
            return response_future

        span.end()
        return response_future

    def _wrap_stream_response(self, span, call):
        try:
            yield from call
        except Exception as exc:
            self.add_error_details_to_span(span, exc)
            raise exc
        finally:
            span.end()


    def tracing_skipped(
        self,
        client_call_details: grpc.ClientCallDetails
    ) -> bool:
        """Returns whether a call is supposed to be skipped for tracing.

        Args:
            client_call_details: A :py:class:`~grpc.ClientCallDetails`-object,
                describing the outgoing RPC.
        
        Returns:
            True if:

            - no filter is set,
            - the :py:class:`~grpc.ClientCallDetails` matches a set filter,
            - the instrumentation is suppressed,

            False otherwise.
        """
        return (
            context.get_value(_SUPPRESS_INSTRUMENTATION_KEY)
            or not self.rpc_matches_filters(client_call_details)
        )

    def rpc_matches_filters(
        self,
        client_call_details: grpc.ClientCallDetails
    ) -> bool:
        """Returns whether the :py:class:`~grpc.ClientCallDetails` matches a
        set `filter_`.

        Args:
            client_call_details: A :py:class:`~grpc.ClientCallDetails`-object,
                describing the outgoing RPC.
        
        Returns:
            True if no filter is set or the :py:class:`~grpc.ClientCallDetails`
            matches a set filter, False otherwise.
        """
        return self._filter is None or self._filter(client_call_details)


class UnaryUnaryClientInterceptor(
    grpc.UnaryUnaryClientInterceptor,
    _BaseClientInterceptor,
):

    def intercept_unary_unary(
        self,
        continuation,
        client_call_details,
        request
    ):
        if self.tracing_skipped(client_call_details):
            return continuation(client_call_details, request)

        with self._start_span(
            client_call_details.method,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            new_details = self.propagate_trace_in_details(client_call_details)

            continuation_with_args = functools.partial(
                continuation, new_details, request
            )

            return self._wrap_unary_response(span, continuation_with_args)


class StreamUnaryClientInterceptor(
    grpc.StreamUnaryClientInterceptor,
    _BaseClientInterceptor,
):

    def intercept_stream_unary(
        self,
        continuation,
        client_call_details,
        request_iterator
    ):
        if self.tracing_skipped(client_call_details):
            return continuation(client_call_details, request_iterator)

        with self._start_span(
            client_call_details.method,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            new_details = self.propagate_trace_in_details(client_call_details)

            continuation_with_args = functools.partial(
                continuation, new_details, request_iterator
            )
            return self._wrap_unary_response(span, continuation_with_args)


class UnaryStreamClientInterceptor(
    grpc.UnaryStreamClientInterceptor,
    _BaseClientInterceptor,
):

    def intercept_unary_stream(
        self,
        continuation,
        client_call_details,
        request
    ):
        if self.tracing_skipped(client_call_details):
            return continuation(client_call_details, request)

        with self._start_span(
            client_call_details.method,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            new_details = self.propagate_trace_in_details(client_call_details)

            resp = continuation(new_details, request)

            return self._wrap_stream_response(span, resp)


class StreamStreamClientInterceptor(
    grpc.StreamStreamClientInterceptor,
    _BaseClientInterceptor,
):

    def intercept_stream_stream(
        self,
        continuation,
        client_call_details,
        request_iterator
    ):
        if self.tracing_skipped(client_call_details):
            return continuation(client_call_details, request_iterator)

        with self._start_span(
            client_call_details.method,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:

            new_details = self.propagate_trace_in_details(client_call_details)

            resp = continuation(new_details, request_iterator)

            return self._wrap_stream_response(span, resp)
