import functools
import json
import logging
import textwrap
from typing import Any, Callable

from arango.api import ApiGroup
from arango.request import Request
from arango.response import Response
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation.arangodb.package import _instruments
from opentelemetry.instrumentation.arangodb.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.attributes import db_attributes, error_attributes
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import StatusCode

logger = logging.getLogger(__name__)


class ArangoDBInstrumentor(BaseInstrumentor):
    """An instrumentor for arangodb module
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
            span_name, kind=SpanKind.CLIENT
        ) as span:
            # We install a custom response handler to get access to the raw response,
            # before the arango client attempts to convert it to one of many different
            # result types.
            original_response_handler = response_handler

            def custom_response_handler(response: Response):
                span.set_attributes(self._get_response_attributes(response))
                return original_response_handler(response)

            span.set_attributes(span_attributes)

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
        bind_vars: dict[str, Any] | None = None
        options: Any | None = None

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

        attributes = {
            db_attributes.DB_SYSTEM_NAME: "arangodb",
            db_attributes.DB_NAMESPACE: instance.db_name,
            db_attributes.DB_OPERATION_NAME: request.endpoint,
            db_attributes.DB_QUERY_TEXT: textwrap.dedent(query.strip("\n")),
        }

        if bind_vars:
            for key, value in bind_vars.items():
                attributes[f"db.query.parameter.{key}"] = json.dumps(value)

        attributes["db.query.options"] = json.dumps(options)

        return span_name, attributes

    def _get_response_attributes(self, response: Response) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            db_attributes.DB_RESPONSE_STATUS_CODE: response.status_code
        }

        attributes["db.execution.cached"] = response.body.get("cached", False)

        if (count := response.body.get("count")) is not None:
            attributes["db.execution.count"] = count

        if extra := response.body.get("extra"):
            stats = extra.get("stats")
            for key, value in stats.items():
                attributes["db.execution.stats." + key] = value

            warnings = extra.get("warnings")
            attributes["db.execution.warnings"] = json.dumps(warnings)

        return attributes
