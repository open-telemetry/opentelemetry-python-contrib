import ddtrace
from ddtrace import config
from ddtrace.http import store_request_headers, store_response_headers

from ddtrace.compat import parse
from ddtrace.constants import ANALYTICS_SAMPLE_RATE_KEY
from ddtrace.ext import SpanTypes, http
from ddtrace.internal.logger import get_logger
from ddtrace.propagation.http import HTTPPropagator
from .constants import DEFAULT_SERVICE

log = get_logger(__name__)

# opentelemetry related
from opentelemetry import context, propagators, trace
from opentelemetry.trace.status import StatusCanonicalCode
from opentelemetry.ext.requests.version import __version__

def _extract_service_name(session, span, hostname=None):
    """Extracts the right service name based on the following logic:
    - `requests` is the default service name
    - users can change it via `session.service_name = 'clients'`
    - if the Span doesn't have a parent, use the set service name or fallback to the default
    parent service value if the set service name is the default
    - if `split_by_domain` is used, always override users settings
    and use the network location as a service name

    The priority can be represented as:
    Updated service name > parent service name > default to `requests`.
    """
    cfg = config.get_from(session)
    if cfg["split_by_domain"] and hostname:
        return hostname

    return cfg["service_name"]

def _wrap_send(func, instance, args, kwargs):
    """Trace the `Session.send` instance method"""
    # avoid instrumenting request towards an exporter
    if context.get_value("suppress_instrumentation"):
        return func(*args, **kwargs)

    tracer = trace.get_tracer(__name__, __version__)

    request = kwargs.get("request") or args[0]
    if not request:
        return func(*args, **kwargs)

    # sanitize url of query
    parsed_uri = parse.urlparse(request.url)
    hostname = parsed_uri.hostname
    if parsed_uri.port:
        hostname = "{}:{}".format(hostname, parsed_uri.port)
    sanitized_url = parse.urlunparse(
        (
            parsed_uri.scheme,
            parsed_uri.netloc,
            parsed_uri.path,
            parsed_uri.params,
            None,  # drop parsed_uri.query
            parsed_uri.fragment,
        )
    )

    with tracer.start_as_current_span("requests.request", kind=trace.SpanKind.CLIENT) as span:
        # update the span service name before doing any action
        span.set_attribute("service", _extract_service_name(instance, span, hostname=hostname))

        # Configure trace search sample rate
        # DEV: analytics enabled on per-session basis
        cfg = config.get_from(instance)
        analytics_enabled = cfg.get("analytics_enabled")
        if analytics_enabled:
            span.set_attribute(ANALYTICS_SAMPLE_RATE_KEY, cfg.get("analytics_sample_rate", True))

        # propagate distributed tracing headers
        if cfg.get("distributed_tracing"):
            propagators.inject(type(request.headers).__setitem__, request.headers)

        # TODO(Mauricio): Re-enable it
        # Storing request headers in the span
        #store_request_headers(request.headers, span, config.requests)

        response = None
        try:
            response = func(*args, **kwargs)

            # TODO(Mauricio): Reenable it
            # Storing response headers in the span. Note that response.headers is not a dict, but an iterable
            # requests custom structure, that we convert to a dict
            #if hasattr(response, "headers"):
            #    store_response_headers(dict(response.headers), span, config.requests)
            return response
        finally:
            try:
                span.set_attribute(http.METHOD, request.method.upper())
                span.set_attribute(http.URL, sanitized_url)
                if config.requests.trace_query_string:
                    span.set_attribute(http.QUERY_STRING, parsed_uri.query)
                if response is not None:
                    span.set_attribute(http.STATUS_CODE, response.status_code)
                    if 400 <= response.status_code:
                        status = trace.Status(StatusCanonicalCode.UNKNOWN, str(response.status_code))
                        span.set_status(status)
                    # Storing response headers in the span.
                    # Note that response.headers is not a dict, but an iterable
                    # requests custom structure, that we convert to a dict
                    # TODO(Mauricio): renable it
                    #response_headers = dict(getattr(response, "headers", {}))
                    #store_response_headers(response_headers, span, config.requests)
            except Exception:
                log.debug("requests: error adding tags", exc_info=True)
