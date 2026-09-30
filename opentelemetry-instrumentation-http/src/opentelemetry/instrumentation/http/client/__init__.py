# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Library agnostic telemetry for HTTP clients.

This package is for authors of HTTP client *instrumentations*, not for
application developers. An instrumentation describes each outgoing request
with :class:`HttpClientRequest` and each response with
:class:`HttpClientResponse`; :class:`HttpClientTelemetry` turns them into HTTP
client spans that follow the `HTTP semantic conventions`_: span name and kind,
required and conditionally required attributes, error status and
``error.type``, redaction of sensitive URL parts, opt-in attributes, and
context propagation.

Every attempt to send a request over the wire is tracked by its own
:class:`HttpClientOperation`, which owns a ``CLIENT`` span.

Creating the telemetry
**********************

Create one :class:`HttpClientTelemetry` per instrumentation, for example when
the instrumentor is enabled, and reuse it for every request. Options are read
once, when the telemetry is created. Combine the options configured through
environment variables with the ones passed in code using
:meth:`HttpClientTelemetryOptions.merge`; options set in the argument win.

.. code-block:: python

    from opentelemetry.instrumentation.http.client import (
        HttpClientTelemetry,
        HttpClientTelemetryOptions,
    )

    # Reads OTEL_PYTHON_REQUESTS_EXCLUDED_URLS, falling back to
    # OTEL_PYTHON_EXCLUDED_URLS, plus the OTEL_INSTRUMENTATION_HTTP_* variables.
    options = HttpClientTelemetryOptions.from_env("REQUESTS").merge(
        HttpClientTelemetryOptions(captured_request_headers=["x-request-id"])
    )
    telemetry = HttpClientTelemetry(
        instrumenting_module_name="opentelemetry.instrumentation.requests",
        instrumenting_library_version="0.1.0",
        tracer_provider=tracer_provider,  # None uses the global provider
        options=options,
    )

Instrumenting a request
***********************

:meth:`HttpClientTelemetry.instrument` starts an operation and returns a
context manager that ends it on exit. An exception raised in the block is
recorded on the span and re-raised unchanged.

.. code-block:: python

    from opentelemetry.instrumentation.http.client import (
        HttpClientConnectionInfo,
        HttpClientRequest,
        HttpClientResponse,
    )


    def send(method, url, headers, body):
        request = HttpClientRequest(
            method=method,
            url=url,
            headers=headers,
            body_size=len(body),
        )
        with telemetry.instrument(request) as operation:
            # Adds e.g. ``traceparent`` to the outgoing headers.
            operation.inject(headers)
            connection = pool.get_connection(url)
            operation.set_connection(
                HttpClientConnectionInfo(
                    server_address=connection.host,
                    server_port=connection.port,
                    network_protocol_version="1.1",
                    network_peer_address=connection.peer_address,
                    network_peer_port=connection.peer_port,
                )
            )
            response = connection.send(method, url, headers, body)
            operation.set_response(
                HttpClientResponse(
                    status_code=response.status,
                    headers=response.headers,
                )
            )
            return response

Starting and ending operations manually
***************************************

When the request does not fit in a ``with`` block, for example with
callbacks or when the response is handed back to the caller before the
operation ends, use :meth:`HttpClientTelemetry.start` and
:meth:`HttpClientOperation.end`. Make sure ``end`` is called exactly once on
every path; later calls have no effect.

.. code-block:: python

    async def send_async(method, url, headers, body):
        operation = telemetry.start(HttpClientRequest(method=method, url=url, headers=headers))
        operation.inject(headers)
        try:
            response = await connection.send(method, url, headers, body)
        except BaseException as exc:
            operation.end(exception=exc)
            raise
        # Sizes that are only known once the request was written.
        operation.set_request_size(body_size=response.request_body_size)
        operation.set_response(HttpClientResponse(status_code=response.status, headers=response.headers))
        operation.end()
        return response

End the operation once the response headers were read, or failed to be read.
Whether reading the response body is included is up to the instrumentation
and should be documented by it, but do not end the operation from the
asynchronous cleanup of a response body the application never read.

Retries and redirects
*********************

Start a new operation for every attempt, including redirects, authentication
challenges and retries after errors, and pass the ordinal of the resend as
``resend_count``. Do not wrap the attempts in an additional logical span.

.. code-block:: python

    for attempt in range(max_attempts):
        request = HttpClientRequest(method="GET", url=url, headers=headers, resend_count=attempt)
        with telemetry.instrument(request) as operation:
            operation.inject(headers)
            response = connection.send("GET", url, headers)
            operation.set_response(HttpClientResponse(status_code=response.status))
        if response.status != 503:
            break

Context propagation
*******************

:meth:`HttpClientOperation.inject` injects the operation's context into the
outgoing request with the propagator passed to :class:`HttpClientTelemetry`,
or the global propagator. Pass a :class:`~opentelemetry.propagators.textmap.Setter`
for carriers that are not mutable string mappings. The context is injected
even when the span is not sampled, so that downstream services make the same
sampling decision, but nothing is injected when HTTP instrumentation is
suppressed or the URL is excluded.

:attr:`HttpClientOperation.context` contains the operation's span but is not
attached to the current context. Attach it with
:func:`opentelemetry.context.attach` only if code running during the request
should see the span as its parent.

Errors and cancellation
***********************

* Responses with a status code of ``400`` or more, or one that cannot be
  interpreted, mark the span as an error with the status code as
  ``error.type``. No extra call is needed.
* Pass the exception that made the request fail to
  :meth:`HttpClientOperation.end`, or record it earlier with
  :meth:`HttpClientOperation.record_exception`. Only the first failure is
  kept. Do not record exceptions that were handled or retried.
* Pass ``error_type`` for a low-cardinality, library-specific identifier
  (for example ``"timeout"``) instead of the exception type name.
* Cancellations (``asyncio.CancelledError``, ``GeneratorExit``,
  ``KeyboardInterrupt``, or ``end(cancelled=True)``) are recorded as errors
  unless the development option ``ignore_cancellation_errors`` is set.

Development options
*******************

Telemetry at the Development stability level of the semantic conventions,
such as ``url.template``, request and response sizes, body content and
``user_agent.synthetic.type``, is configured with
:class:`~opentelemetry.instrumentation.http.client._incubating.HttpClientTelemetryDevelopmentOptions`.

.. warning::
    Development options do NOT follow semantic versioning and may have
    BREAKING changes in any release, including minor and patch releases.

.. code-block:: python

    from opentelemetry.instrumentation.http.client._incubating import (
        HttpClientTelemetryDevelopmentOptions,
    )

    telemetry = HttpClientTelemetry(
        instrumenting_module_name="opentelemetry.instrumentation.requests",
        options=HttpClientTelemetryOptions.from_env("REQUESTS"),
        development_options=HttpClientTelemetryDevelopmentOptions.from_env().merge(
            HttpClientTelemetryDevelopmentOptions(capture_url_template=True)
        ),
    )
    # With capture_url_template, the span is named "GET /users/{id}".
    request = HttpClientRequest(method="GET", url="https://example.com/users/42", url_template="/users/{id}")

Capturing body content
======================

``http.request.body.content`` and ``http.response.body.content`` are only
recorded when ``capture_request_body_content`` or
``capture_response_body_content`` is set in code. Pass the body chunks as the
HTTP client sends or the application receives them; the content is recorded
when the operation ends.

.. code-block:: python

    telemetry = HttpClientTelemetry(
        instrumenting_module_name="opentelemetry.instrumentation.requests",
        development_options=HttpClientTelemetryDevelopmentOptions(
            capture_request_body_content=True,
            capture_response_body_content=True,
            body_content_max_size=4096,
        ),
    )


    def traced_body(operation, chunks):
        for chunk in chunks:
            operation.add_request_body(chunk)
            yield chunk


    operation = telemetry.start(HttpClientRequest(method="POST", url=url, headers={"content-type": "application/json"}))
    response = connection.send("POST", url, traced_body(operation, chunks))
    operation.set_response(HttpClientResponse(status_code=response.status, headers=response.headers))
    operation.add_response_body(response.content)
    operation.end()

* Body content may contain sensitive information. Set
  ``body_content_max_size``; content is unbounded otherwise.
* Only bodies whose ``Content-Type`` is textual are recorded, decoded with the
  declared ``charset`` (UTF-8 by default). Binary bodies are skipped because
  span attributes cannot hold byte arrays.
* Pass content with any ``Content-Encoding`` (gzip, br, ...) removed.
* Never read, rewind or close body streams just to capture them.
* Chunks passed after the operation ended are ignored, so response bodies are
  often recorded partially or not at all.

Caveats
*******

* ``headers`` of :class:`HttpClientRequest` and :class:`HttpClientResponse`
  must have lowercase names, or be a case-insensitive mapping. Headers are
  read when the request starts and when the response is set; later changes
  are not seen.
* Pass the absolute request ``url``. Credentials and sensitive query
  parameter values are redacted from ``url.full``. A URL that cannot be parsed
  is not recorded.
* Attributes that samplers can use (``http.request.method``,
  ``server.address``, ``server.port``, ``url.full`` and opted-in attributes)
  are set when the operation starts. Pass ``server_address`` and
  ``server_port`` in the request when they differ from the URL, for example
  when a ``Host`` header overrides it.
* Unknown HTTP methods are recorded as ``_OTHER``, and their spans are named
  ``HTTP``. Methods are case-sensitive: ``get`` is unknown. See the
  ``known_methods`` and ``capture_all_methods`` options.
* When the instrumented client is built on another instrumented HTTP client
  (for example requests on urllib3), send the request inside
  ``opentelemetry.instrumentation.utils.suppress_http_instrumentation()`` to
  avoid duplicate client spans.
* Only spans are emitted today. ``meter_provider``,
  :meth:`HttpClientTelemetry.start_connection` and
  :class:`HttpClientConnection` are accepted, but record no metrics yet.

References
**********

* `HTTP semantic conventions`_
* :mod:`opentelemetry.instrumentation.http.environment_variables`
* :mod:`opentelemetry.instrumentation.http.client._incubating.environment_variables`

.. _HTTP semantic conventions: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/http/http-spans.md
"""

# pylint: disable=useless-import-alias
from opentelemetry.instrumentation.http.client._connection import (
    HttpClientConnection as HttpClientConnection,
)
from opentelemetry.instrumentation.http.client._connection import (
    HttpClientConnectionInfo as HttpClientConnectionInfo,
)
from opentelemetry.instrumentation.http.client._connection import (
    HttpClientConnectionState as HttpClientConnectionState,
)
from opentelemetry.instrumentation.http.client._operation import (
    HttpClientOperation as HttpClientOperation,
)
from opentelemetry.instrumentation.http.client._operation import (
    HttpClientResponse as HttpClientResponse,
)
from opentelemetry.instrumentation.http.client._options import (
    HttpClientTelemetryOptions as HttpClientTelemetryOptions,
)
from opentelemetry.instrumentation.http.client._telemetry import (
    HttpClientRequest as HttpClientRequest,
)
from opentelemetry.instrumentation.http.client._telemetry import (
    HttpClientTelemetry as HttpClientTelemetry,
)
