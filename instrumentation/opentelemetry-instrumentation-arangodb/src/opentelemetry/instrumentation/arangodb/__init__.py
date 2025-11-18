import functools
import json
import logging
import textwrap
from typing import Any, Callable, Union
from urllib.parse import urlparse

from arango.api import ApiGroup
from arango.request import Request
from arango.response import Response
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation.arangodb import arangodb_attributes
from opentelemetry.instrumentation.arangodb.package import _instruments
from opentelemetry.instrumentation.arangodb.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.attributes import (
    db_attributes,
    error_attributes,
    server_attributes,
)
from opentelemetry.trace import Span, SpanKind
from opentelemetry.trace.status import StatusCode

logger = logging.getLogger(__name__)


class ArangoDBInstrumentor(BaseInstrumentor):
    """An instrumentor for arangodb module.

    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self):
        return _instruments

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get(
            "tracer_provider", trace.get_tracer_provider()
        )

        tracer = trace.get_tracer(
            __name__, __version__, tracer_provider=tracer_provider
        )

        if hasattr(ApiGroup, "_execute"):
            wrap_function_wrapper(
                "arango.api",
                "ApiGroup._execute",
                functools.partial(self.execute_with_span, tracer=tracer),
            )

    def _uninstrument(self, **kwargs):
        if hasattr(ApiGroup, "_execute"):
            unwrap(ApiGroup, "_execute")

    def execute_with_span(
        self,
        wrapped: Callable[..., Any],
        instance: ApiGroup,
        args,
        kwargs,
        *,
        tracer: trace.Tracer,
    ) -> Any:
        request, response_handler = args

        span_name, span_attributes = self._get_request_attributes(
            instance, request
        )

        with tracer.start_as_current_span(
            span_name, kind=SpanKind.CLIENT, attributes=span_attributes
        ) as span:
            # We install a custom response handler to get access to the raw response,
            # before the arango client attempts to convert it to one of many different
            # result types.
            original_response_handler = response_handler

            def custom_response_handler(response: Response):
                span.set_attributes(self._get_response_attributes(response))
                self._add_span_events(span, response)

                return original_response_handler(response)

            try:
                result = wrapped(request, custom_response_handler)
                span.set_status(StatusCode.OK)
            except Exception as e:
                span.set_attribute(
                    error_attributes.ERROR_TYPE, type(e).__name__
                )
                span.set_status(StatusCode.ERROR, str(e))
                raise e

            return result

    def _get_request_attributes(
        self, instance: ApiGroup, request: Request
    ) -> tuple[str, dict[str, Any]]:
        attributes = {}

        query: str = ""
        bind_vars: Union[dict[str, Any], None] = None
        options: Union[Any, None] = None

        span_name = f"ArangoDB: {request.method.upper()} {request.endpoint}"

        if isinstance(request.data, dict):
            if "query" in request.data:
                query = str(request.data.get("query"))
                bind_vars = request.data.get("bindVars")
                options = request.data.get("options")

            else:
                query = str(request.data)

        else:
            query = str(request.data)

        endpoint = urlparse(instance.conn._hosts[0])

        attributes: dict[str, Any] = {
            db_attributes.DB_SYSTEM_NAME: "arangodb",
            server_attributes.SERVER_ADDRESS: endpoint.hostname,
            server_attributes.SERVER_PORT: endpoint.port,
            db_attributes.DB_NAMESPACE: instance.db_name,
            db_attributes.DB_OPERATION_NAME: request.endpoint,
            db_attributes.DB_QUERY_TEXT: textwrap.dedent(query.strip("\n")),
        }

        if bind_vars:
            for key, value in bind_vars.items():
                attributes[f"db.query.parameter.{key}"] = json.dumps(value)

        if options and isinstance(options, dict):
            if "allowDirtyReads" in options:
                attributes[arangodb_attributes.ALLOW_DIRTY_READS] = (
                    options.get("allowDirtyReads")
                )
            if "cache" in options:
                attributes[arangodb_attributes.CACHE] = options.get("cache")
            if "stream" in options:
                attributes[arangodb_attributes.STREAM] = options.get("stream")

        return span_name, attributes

    def _get_response_attributes(self, response: Response) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            db_attributes.DB_RESPONSE_STATUS_CODE: response.status_code
        }

        if "cached" in response.body:
            attributes[arangodb_attributes.RESPONSE_CACHED] = (
                response.body.get("cached")
            )
        if "count" in response.body:
            attributes[arangodb_attributes.RESPONSE_COUNT] = response.body.get(
                "count"
            )

        return attributes

    def _add_span_events(self, span: Span, response: Response):
        if extra := response.body.get("extra"):
            if warnings := extra.get("warnings"):
                for warning in warnings:
                    span.add_event(
                        "ArangoDB Warning",
                        {
                            "code": warning.get("code"),
                            "message": warning.get("message"),
                        },
                    )
