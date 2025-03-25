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

import functools
import logging
from collections import OrderedDict
from typing import Any, Callable, MutableMapping

import grpc
from grpc._interceptor import _ClientCallDetails

from opentelemetry import trace
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from opentelemetry.propagate import inject
from opentelemetry.propagators.textmap import Setter
from opentelemetry.semconv.trace import RpcSystemValues, SpanAttributes
from opentelemetry.trace.status import Status, StatusCode

logger = logging.getLogger(__name__)


class _CarrierSetter(Setter):
    """We use a custom setter in order to be able to lower case
    keys as is required by grpc.
    """

    def set(self, carrier: MutableMapping[str, str], key: str, value: str):
        carrier[key.lower()] = value


_carrier_setter = _CarrierSetter()


def _unary_done_callback(
    span: trace.Span, hook_callback: Callable[[trace.Span, Any], None]
):
    def callback(response_future: grpc.Future):
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
            else:
                if hook_callback:
                    hook_callback(span, response_future.result())

    return callback


def _safe_invoke(function: Callable, *args):
    function_name = "<unknown>"
    try:
        function_name = function.__name__
        function(*args)
    except Exception as ex:  # pylint:disable=broad-except
        logger.error(
            "Error when invoking function '%s'", function_name, exc_info=ex
        )


class _BaseClientInterceptor:
    """Base for client interceptors.
    Supplies convenient functions which are required by all four client
    interceptors.
    """

    def __init__(
        self, tracer, filter_=None, request_hook=None, response_hook=None
    ):
        self._tracer = tracer
        self._filter = filter_
        self._request_hook = request_hook
        self._response_hook = response_hook

    def _call_request_hook(self, span: trace.Span, request):
        if not callable(self._request_hook):
            return
        _safe_invoke(self._request_hook, span, request)

    def _call_response_hook(self, span: trace.Span, response):
        if not callable(self._response_hook):
            return
        _safe_invoke(self._response_hook, span, response)

    @staticmethod
    def propagate_trace_in_details(client_call_details):
        """Propagates the trace into the metadata of the call.
        Args:
            client_call_details: The original
                :py:class:`~grpc.ClientCallDetails`, describing the outgoing
                RPC.
        Returns:
            An adapted version of the original
            :py:class:`~grpc.ClientCallDetails`, describing the outgoing RPC,
            whereby the metadata contains the trace ID.
        """
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
            # credentials, wait_for_ready, and compression, depending on
            # grpc-version
            *client_call_details[3:],
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

    def _wrap_unary_response(self, span: trace.Span, continuation):
        """Wraps a unary-response-RPC to record a possible exception.

        Args:
            span: The active span.
            continuation: A callable which is created by:

                .. code-block:: python

                functools.partial(
                    continuation, client_call_details, request_or_iterator
                )

        Returns:
            The response if the RPC is called synchronously, or the
            :py:class:`~grpc.Future` if the RPC is called asynchronously.
        """
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
        if isinstance(response_future, grpc.Future):
            response_future.add_done_callback(
                _unary_done_callback(
                    span,
                    self._call_response_hook if self._response_hook else None,
                )
            )
            return response_future

        if self._response_hook:
            self._call_response_hook(span, response_future)
        span.end()
        return response_future

    def _wrap_stream_response(self, span: trace.Span, call):
        """Wraps a stream-response-RPC to record a possible exception.

        Args:
            span: The active span.
            call: The response iterator which is created by:

                .. code-block:: python

                continuation(client_call_details, request_or_iterator)

        Returns:
            The response iterator.
        """
        try:
            yield from call
        except Exception as exc:
            self.add_error_details_to_span(span, exc)
            raise exc
        finally:
            span.end()


class UnaryUnaryClientInterceptor(
    grpc.UnaryUnaryClientInterceptor,
    _BaseClientInterceptor,
):
    def intercept_unary_unary(
        self, continuation, client_call_details, request
    ):
        if not is_instrumentation_enabled():
            return continuation(client_call_details, request)

        if self._filter is not None and not self._filter(client_call_details):
            return continuation(client_call_details, request)

        with self._start_span(
            client_call_details.method,
            end_on_exit=False,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            if self._request_hook:
                self._call_request_hook(span, request)

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
        self, continuation, client_call_details, request_iterator
    ):
        if not is_instrumentation_enabled():
            return continuation(client_call_details, request_iterator)

        if self._filter is not None and not self._filter(client_call_details):
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
        self, continuation, client_call_details, request
    ):
        if not is_instrumentation_enabled():
            return continuation(client_call_details, request)

        if self._filter is not None and not self._filter(client_call_details):
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
        self, continuation, client_call_details, request_iterator
    ):
        if not is_instrumentation_enabled():
            return continuation(client_call_details, request_iterator)

        if self._filter is not None and not self._filter(client_call_details):
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
