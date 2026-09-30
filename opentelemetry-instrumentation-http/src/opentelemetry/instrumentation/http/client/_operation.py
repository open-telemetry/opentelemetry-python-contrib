# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING

from opentelemetry.context import Context
from opentelemetry.instrumentation.http._internal._body import (
    CONTENT_TYPE_HEADER,
    BodyContentCapture,
    is_textual_content_type,
)
from opentelemetry.instrumentation.http._internal._errors import (
    get_error_type,
    is_cancellation,
    is_error_status_code,
)
from opentelemetry.instrumentation.http._internal._headers import (
    get_header_value,
)
from opentelemetry.instrumentation.http._internal._http import (
    get_request_size_attributes,
    get_response_size_attributes,
    get_status_code_attributes,
)
from opentelemetry.instrumentation.http._internal._network import (
    get_peer_attributes,
    get_protocol_attributes,
    get_transport_attributes,
)
from opentelemetry.instrumentation.http._internal._semconv import (
    HTTP_REQUEST_BODY_CONTENT,
    HTTP_RESPONSE_BODY_CONTENT,
)
from opentelemetry.instrumentation.http.client._connection import (
    HttpClientConnectionInfo,
)
from opentelemetry.propagate import get_global_textmap
from opentelemetry.propagators.textmap import (
    CarrierT,
    Setter,
    default_setter,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace import Span, Status, StatusCode

if TYPE_CHECKING:
    from opentelemetry.instrumentation.http.client._telemetry import (
        HttpClientTelemetry,
    )


@dataclass(frozen=True, kw_only=True, slots=True)
class HttpClientResponse:
    """Library-agnostic description of a received HTTP response.

    Attributes:
        headers: Response headers. Names must be lowercase, or ``headers``
            must be a case-insensitive mapping. Values are a single string or
            a sequence of values.
    """

    status_code: int | None = None
    headers: Mapping[str, str | Sequence[str]] | None = None
    body_size: int | None = None
    total_size: int | None = None


class HttpClientOperation:
    """Telemetry for a single HTTP client request attempt."""

    def __init__(
        self,
        span: Span,
        context: Context,
        telemetry: HttpClientTelemetry,
        *,
        propagate: bool = True,
        request_content_type: str | None = None,
    ) -> None:
        self._span = span
        self._context = context
        self._telemetry = telemetry
        self._propagate = propagate
        self._request_content_type = request_content_type
        self._response_content_type: str | None = None
        # pylint: disable=protected-access
        recording = span.is_recording()
        self._request_body = (
            BodyContentCapture(telemetry._body_content_max_size)
            if recording
            and telemetry._capture_request_body_content
            and is_textual_content_type(request_content_type)
            else None
        )
        self._response_body = (
            BodyContentCapture(telemetry._body_content_max_size)
            if recording and telemetry._capture_response_body_content
            else None
        )
        # pylint: enable=protected-access
        self._ended = False
        self._status_code: int | None = None
        self._error_recorded = False

    @property
    def span(self) -> Span:
        """The span tracking this operation."""
        return self._span

    @property
    def context(self) -> Context:
        """The context containing this operation's span."""
        return self._context

    def inject(
        self,
        carrier: CarrierT,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        """Inject this operation's context into the outgoing request carrier.

        Uses the telemetry's propagator, or the global propagator when none was
        given. The context is injected even when the span is not sampled, but
        nothing is injected for excluded URLs or when HTTP instrumentation is
        suppressed.
        """
        if not self._propagate:
            return
        # pylint: disable-next=protected-access
        propagator = self._telemetry._propagator
        if propagator is None:
            propagator = get_global_textmap()
        propagator.inject(carrier, context=self._context, setter=setter)

    def set_connection(self, connection: HttpClientConnectionInfo) -> None:
        """Record the connection used for this request attempt.

        Call this once the connection is acquired.
        """
        if not self._span.is_recording():
            return
        attributes = get_peer_attributes(connection.network_peer_address, connection.network_peer_port) | (
            get_protocol_attributes(connection.network_protocol_name, connection.network_protocol_version)
        )
        # pylint: disable-next=protected-access
        if self._telemetry._capture_network_transport:
            attributes |= get_transport_attributes(connection.network_transport)
        self._span.set_attributes(attributes)

    def set_response(self, response: HttpClientResponse) -> None:
        """Record the received response."""
        if not self._span.is_recording():
            return
        self._status_code = response.status_code
        telemetry = self._telemetry
        if self._response_body is not None:
            self._response_content_type = get_header_value(response.headers, CONTENT_TYPE_HEADER)
            # Stop buffering content that will not be recorded.
            if not is_textual_content_type(self._response_content_type):
                self._response_body = None
        # pylint: disable=protected-access
        self._span.set_attributes(
            get_status_code_attributes(response.status_code)
            | telemetry._response_headers.get_attributes(response.headers)
            | get_response_size_attributes(
                response.body_size,
                response.total_size,
                capture_body_size=telemetry._capture_response_body_size,
                capture_size=telemetry._capture_response_size,
            )
        )
        # pylint: enable=protected-access
        # An error status code takes precedence over a previously recorded error type.
        if self._error_recorded and response.status_code is not None and is_error_status_code(response.status_code):
            self._span.set_attribute(ERROR_TYPE, str(response.status_code))

    def set_request_size(self, *, body_size: int | None = None, total_size: int | None = None) -> None:
        """Record request sizes that were not known when the operation started.

        Later calls overwrite values set by earlier ones; unset sizes leave them unchanged.
        """
        if not self._span.is_recording():
            return
        telemetry = self._telemetry
        # pylint: disable=protected-access
        self._span.set_attributes(
            get_request_size_attributes(
                body_size,
                total_size,
                capture_body_size=telemetry._capture_request_body_size,
                capture_size=telemetry._capture_request_size,
            )
        )
        # pylint: enable=protected-access

    def add_request_body(self, chunk: bytes) -> None:
        """Record a chunk of the request body as it is sent.

        Only has an effect when ``capture_request_body_content`` is enabled.
        Pass the bytes the application sent, with any content coding indicated
        by ``Content-Encoding`` removed. Do not read or rewind body streams
        just to call this: pass chunks as the HTTP client sends them. The
        content is recorded when the operation ends, chunks passed after
        :meth:`end` are ignored. Nothing is buffered when the request
        ``Content-Type`` is not textual.
        """
        if self._ended or self._request_body is None:
            return
        self._request_body.add(chunk)

    def add_response_body(self, chunk: bytes) -> None:
        """Record a chunk of the response body as it is received.

        Only has an effect when ``capture_response_body_content`` is enabled.
        Pass the bytes the application received, with any content coding
        indicated by ``Content-Encoding`` removed. Do not read body streams
        just to call this: pass chunks as the application consumes them. The
        content is recorded when the operation ends, so only the part of the
        body received by then is recorded; chunks passed after :meth:`end` are
        ignored. The ``Content-Type`` is taken from the headers passed to
        :meth:`set_response`; chunks passed after it indicates non-textual
        content are not buffered.
        """
        if self._ended or self._response_body is None:
            return
        self._response_body.add(chunk)

    def record_exception(self, exception: BaseException, *, error_type: str | None = None) -> None:
        """Record an exception that made the request fail.

        The exception, error status and ``error.type`` are recorded
        immediately. Only the first recorded failure is kept: later calls, and
        the ``exception`` and ``error_type`` passed to :meth:`end`, are
        ignored. Do not use this for exceptions that were handled or retried.
        """
        if not self._span.is_recording():
            return
        if self._ignores_cancellation() and is_cancellation(exception):
            return
        self._record_error(exception, error_type)

    def end(
        self,
        *,
        exception: BaseException | None = None,
        error_type: str | None = None,
        cancelled: bool = False,
        end_time: int | None = None,
    ) -> None:
        """End the operation. Calling this more than once has no effect.

        Call this once the response headers have been fully read, or have
        failed to be read. Reading the response body may or may not be
        included, but do not defer ending the operation to an asynchronous
        cleanup of an unread response.

        ``exception`` and ``error_type`` are ignored if a failure was already
        recorded with :meth:`record_exception`.

        ``error.type`` is recorded as, in order of precedence: the response
        status code as a string when it indicates an error, ``error_type``
        (``_OTHER`` when empty) or the fully qualified type name of
        ``exception`` (without the ``builtins.`` prefix).

        Args:
            exception: The exception that made the request fail, if any.
            error_type: Low-cardinality identifier of the error, if any.
                Recorded as ``error.type`` unless an error status code was
                received.
            cancelled: The caller cancelled the request. Cancellations are not
                recorded as errors when ``ignore_cancellation_errors`` is set;
                ``asyncio.CancelledError``, ``GeneratorExit`` and
                ``KeyboardInterrupt`` exceptions are always treated as
                cancellations. Without ``exception`` or ``error_type``, no
                error is recorded.
            end_time: End time of the operation in nanoseconds since the epoch.
        """
        if self._ended:
            return
        self._ended = True
        if self._span.is_recording():
            if self._ignores_cancellation() and (cancelled or is_cancellation(exception)):
                exception, error_type = None, None
            self._record_error(exception, error_type)
            self._record_body_content()
        self._span.end(end_time=end_time)

    def _record_body_content(self) -> None:
        attributes = _get_body_content_attributes(
            HTTP_REQUEST_BODY_CONTENT, self._request_body, self._request_content_type
        ) | _get_body_content_attributes(HTTP_RESPONSE_BODY_CONTENT, self._response_body, self._response_content_type)
        if attributes:
            self._span.set_attributes(attributes)

    def _ignores_cancellation(self) -> bool:
        return self._telemetry._ignore_cancellation_errors  # pylint: disable=protected-access

    def _record_error(self, exception: BaseException | None, error_type: str | None) -> None:
        if self._error_recorded:
            return
        final_error_type = get_error_type(self._status_code, error_type, exception)
        if final_error_type is None:
            return
        self._error_recorded = True
        description = None
        if exception is not None:
            self._span.record_exception(exception)
            description = str(exception) or None
        self._span.set_attribute(ERROR_TYPE, final_error_type)
        self._span.set_status(Status(StatusCode.ERROR, description))


def _get_body_content_attributes(key: str, body: BodyContentCapture | None, content_type: str | None) -> dict[str, str]:
    if body is None:
        return {}
    content = body.get_content(content_type)
    if content is None:
        return {}
    return {key: content}


class _InstrumentedRequest:
    """Context manager that ends its operation on exit."""

    def __init__(self, operation: HttpClientOperation) -> None:
        self._operation = operation

    def __enter__(self) -> HttpClientOperation:
        return self._operation

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._operation.end(exception=exc_value)
