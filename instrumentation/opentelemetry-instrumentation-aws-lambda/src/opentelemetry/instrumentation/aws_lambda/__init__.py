# Copyright 2020, OpenTelemetry Authors
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

"""
The opentelemetry-instrumentation-aws-lambda package provides an Instrumentor
to traces calls within a Python AWS Lambda function.

Usage
-----

.. code:: python

    # Copy this snippet into an AWS Lambda function

    import boto3
    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
    from opentelemetry.instrumentation.aws_lambda import AwsLambdaInstrumentor

    # Enable instrumentation
    BotocoreInstrumentor().instrument()
    AwsLambdaInstrumentor().instrument()

    # Lambda function
    def lambda_handler(event, context):
        s3 = boto3.resource('s3')
        for bucket in s3.buckets.all():
            print(bucket.name)

        return "200 OK"

API
---

The `instrument` method accepts the following keyword args:

tracer_provider (TracerProvider) - an optional tracer provider
meter_provider (MeterProvider) - an optional meter provider
event_context_extractor (Callable) - a function that returns an OTel Trace
Context given the Lambda Event the AWS Lambda was invoked with
this function signature is: def event_context_extractor(lambda_event: Any) -> Context
for example:

.. code:: python

    from opentelemetry.instrumentation.aws_lambda import AwsLambdaInstrumentor

    def custom_event_context_extractor(lambda_event):
        # If the `TraceContextTextMapPropagator` is the global propagator, we
        # can use it to parse out the context from the HTTP Headers.
        return get_global_textmap().extract(lambda_event["foo"]["headers"])

    AwsLambdaInstrumentor().instrument(
        event_context_extractor=custom_event_context_extractor
    )

---
"""

import logging
import os
import time
from importlib import import_module
from typing import Any, Callable, Collection, Optional, Sequence
from urllib.parse import urlencode

from wrapt import wrap_function_wrapper

from opentelemetry.context.context import Context
from opentelemetry.instrumentation.aws_lambda.package import _instruments
from opentelemetry.instrumentation.aws_lambda.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import MeterProvider, get_meter_provider
from opentelemetry.propagate import get_global_textmap
from opentelemetry.propagators.aws.aws_xray_propagator import (
    TRACE_HEADER_KEY,
    AwsXRayPropagator,
)
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import (
    Link,
    Span,
    SpanKind,
    TracerProvider,
    get_tracer,
    get_tracer_provider,
)
from opentelemetry.trace.propagation import get_current_span

logger = logging.getLogger(__name__)

_HANDLER = "_HANDLER"
_X_AMZN_TRACE_ID = "_X_AMZN_TRACE_ID"
ORIG_HANDLER = "ORIG_HANDLER"
OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT = (
    "OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT"
)
OTEL_LAMBDA_USE_AWS_CONTEXT_PROPAGATION = "OTEL_LAMBDA_USE_AWS_CONTEXT_PROPAGATION"


def _default_event_context_extractor(lambda_event: Any) -> Context:
    """Default way of extracting the context from the Lambda Event.

    Assumes the Lambda Event is a map with the headers under the 'headers' key.
    This is the mapping to use when the Lambda is invoked by an API Gateway
    REST API where API Gateway is acting as a pure proxy for the request.
    Protects headers from being something other than dictionary, as this
    is what downstream propagators expect.

    See more:
    https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format

    Args:
        lambda_event: user-defined, so it could be anything, but this
            method counts on it being a map with a 'headers' key
    Returns:
        A Context with configuration found in the event.
    """
    headers = None
    try:
        headers = lambda_event["headers"]
    except (TypeError, KeyError):
        logger.debug(
            "Extracting context from Lambda Event failed: either enable X-Ray active tracing or configure API Gateway to trigger this Lambda function as a pure proxy. Otherwise, generated spans will have an invalid (empty) parent context."
        )
    if not isinstance(headers, dict):
        headers = {}
    return get_global_textmap().extract(headers)


def _determine_parent_context(
    lambda_event: Any,
    use_aws_context_propagation: bool,
    event_context_extractor: Callable[[Any], Context],
) -> Context:
    """Determine the parent context for the current Lambda invocation.

    See more:
    https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/instrumentation/aws-lambda.md

    Args:
        lambda_event: user-defined, so it could be anything, but this
            method counts it being a map with a 'headers' key
        event_context_extractor: a method which takes the Lambda
            Event as input and extracts an OTel Context from it. By default,
            the context is extracted from the HTTP headers of an API Gateway
            request.
    Returns:
        A Context with configuration found in the carrier.
    """
    parent_context = None
    if use_aws_context_propagation:
        parent_context = _get_x_ray_context()
    elif event_context_extractor:
        parent_context = event_context_extractor(lambda_event)
    else:
        parent_context = _default_event_context_extractor(lambda_event)

    return parent_context


def _get_x_ray_context() -> Optional[Context]:
    """Determine teh context propagated through the lambda runtime"""
    xray_env_var = os.environ.get(_X_AMZN_TRACE_ID)
    if xray_env_var:
        env_context = AwsXRayPropagator().extract({TRACE_HEADER_KEY: xray_env_var})
        return env_context

    return None


def _determine_links() -> Optional[Sequence[Link]]:
    """Determine if a Link should be added to the Span based on the
    environment variable `_X_AMZN_TRACE_ID`.


    See more:
    https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/instrumentation/aws-lambda.md#aws-x-ray-environment-span-link

    Returns:
        A Link or None
    """
    links = None

    x_ray_context = _get_x_ray_context()

    if x_ray_context:
        span_context = get_current_span(x_ray_context).get_span_context()
        if span_context.is_valid:
            links = [Link(span_context, {"source": "x-ray-env"})]

    return links


def _set_api_gateway_v1_proxy_attributes(lambda_event: Any, span: Span) -> Span:
    """Sets HTTP attributes for REST APIs and v1 HTTP APIs

    More info:
    https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format
    """
    span.set_attribute(SpanAttributes.HTTP_METHOD, lambda_event.get("httpMethod"))

    if lambda_event.get("headers"):
        if "User-Agent" in lambda_event["headers"]:
            span.set_attribute(
                SpanAttributes.HTTP_USER_AGENT,
                lambda_event["headers"]["User-Agent"],
            )
        if "X-Forwarded-Proto" in lambda_event["headers"]:
            span.set_attribute(
                SpanAttributes.HTTP_SCHEME,
                lambda_event["headers"]["X-Forwarded-Proto"],
            )
        if "Host" in lambda_event["headers"]:
            span.set_attribute(
                SpanAttributes.NET_HOST_NAME,
                lambda_event["headers"]["Host"],
            )
    if "resource" in lambda_event:
        span.set_attribute(SpanAttributes.HTTP_ROUTE, lambda_event["resource"])

        if lambda_event.get("queryStringParameters"):
            span.set_attribute(
                SpanAttributes.HTTP_TARGET,
                f"{lambda_event['resource']}?{urlencode(lambda_event['queryStringParameters'])}",
            )
        else:
            span.set_attribute(SpanAttributes.HTTP_TARGET, lambda_event["resource"])

    return span


def _set_api_gateway_v2_proxy_attributes(lambda_event: Any, span: Span) -> Span:
    """Sets HTTP attributes for v2 HTTP APIs

    More info:
    https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html
    """
    if "domainName" in lambda_event["requestContext"]:
        span.set_attribute(
            SpanAttributes.NET_HOST_NAME,
            lambda_event["requestContext"]["domainName"],
        )

    if lambda_event["requestContext"].get("http"):
        if "method" in lambda_event["requestContext"]["http"]:
            span.set_attribute(
                SpanAttributes.HTTP_METHOD,
                lambda_event["requestContext"]["http"]["method"],
            )
        if "userAgent" in lambda_event["requestContext"]["http"]:
            span.set_attribute(
                SpanAttributes.HTTP_USER_AGENT,
                lambda_event["requestContext"]["http"]["userAgent"],
            )
        if "path" in lambda_event["requestContext"]["http"]:
            span.set_attribute(
                SpanAttributes.HTTP_ROUTE,
                lambda_event["requestContext"]["http"]["path"],
            )
            if lambda_event.get("rawQueryString"):
                span.set_attribute(
                    SpanAttributes.HTTP_TARGET,
                    f"{lambda_event['requestContext']['http']['path']}?{lambda_event['rawQueryString']}",
                )
            else:
                span.set_attribute(
                    SpanAttributes.HTTP_TARGET,
                    lambda_event["requestContext"]["http"]["path"],
                )

    return span


def _instrument(
    wrapped_module_name,
    wrapped_function_name,
    flush_timeout,
    event_context_extractor: Callable[[Any], Context],
    tracer_provider: TracerProvider = None,
    meter_provider: MeterProvider = None,
    use_aws_context_propagation: bool = False,
):
    def _instrumented_lambda_handler_call(  # noqa pylint: disable=too-many-branches
        call_wrapped, instance, args, kwargs
    ):
        orig_handler_name = ".".join([wrapped_module_name, wrapped_function_name])

        lambda_event = args[0]

        # We are not fully complying with the specification here to be backwards
        # compatible with the old version of the specification.
        # the ``use_aws_context_propagation`` flag allow us
        # to opt-in into the previous behavior
        parent_context = _determine_parent_context(
            lambda_event, use_aws_context_propagation, event_context_extractor
        )

        links = None
        if not use_aws_context_propagation:
            links = _determine_links()

        span_kind = None
        try:
            if lambda_event["Records"][0]["eventSource"] in {
                "aws:sqs",
                "aws:s3",
                "aws:sns",
                "aws:dynamodb",
            }:
                # See more:
                # https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html
                # https://docs.aws.amazon.com/lambda/latest/dg/with-sns.html
                # https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html
                # https://docs.aws.amazon.com/lambda/latest/dg/with-ddb.html
                span_kind = SpanKind.CONSUMER
            else:
                span_kind = SpanKind.SERVER
        except (IndexError, KeyError, TypeError):
            span_kind = SpanKind.SERVER

        tracer = get_tracer(__name__, __version__, tracer_provider)

        with tracer.start_as_current_span(
            name=orig_handler_name,
            context=parent_context,
            kind=span_kind,
            links=links,
        ) as span:
            if span.is_recording():
                lambda_context = args[1]
                # NOTE: The specs mention an exception here, allowing the
                # `ResourceAttributes.FAAS_ID` attribute to be set as a span
                # attribute instead of a resource attribute.
                #
                # See more:
                # https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/faas.md#example
                span.set_attribute(
                    ResourceAttributes.FAAS_ID,
                    lambda_context.invoked_function_arn,
                )
                span.set_attribute(
                    SpanAttributes.FAAS_EXECUTION,
                    lambda_context.aws_request_id,
                )

            result = call_wrapped(*args, **kwargs)

            # If the request came from an API Gateway, extract http attributes from the event
            # https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/instrumentation/aws-lambda.md#api-gateway
            # https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/http.md#http-server-semantic-conventions
            if isinstance(lambda_event, dict) and lambda_event.get("requestContext"):
                span.set_attribute(SpanAttributes.FAAS_TRIGGER, "http")

                if lambda_event.get("version") == "2.0":
                    _set_api_gateway_v2_proxy_attributes(lambda_event, span)
                else:
                    _set_api_gateway_v1_proxy_attributes(lambda_event, span)

                if isinstance(result, dict) and result.get("statusCode"):
                    span.set_attribute(
                        SpanAttributes.HTTP_STATUS_CODE,
                        result.get("statusCode"),
                    )

        now = time.time()
        _tracer_provider = tracer_provider or get_tracer_provider()
        if hasattr(_tracer_provider, "force_flush"):
            try:
                # NOTE: `force_flush` before function quit in case of Lambda freeze.
                _tracer_provider.force_flush(flush_timeout)
            except Exception:  # pylint: disable=broad-except
                logger.exception("TracerProvider failed to flush traces")
        else:
            logger.warning(
                "TracerProvider was missing `force_flush` method. This is necessary in case of a Lambda freeze and would exist in the OTel SDK implementation."
            )

        _meter_provider = meter_provider or get_meter_provider()
        if hasattr(_meter_provider, "force_flush"):
            rem = flush_timeout - (time.time() - now) * 1000
            if rem > 0:
                try:
                    # NOTE: `force_flush` before function quit in case of Lambda freeze.
                    _meter_provider.force_flush(rem)
                except Exception:  # pylint: disable=broad-except
                    logger.exception("MeterProvider failed to flush metrics")
        else:
            logger.warning(
                "MeterProvider was missing `force_flush` method. This is necessary in case of a Lambda freeze and would exist in the OTel SDK implementation."
            )

        return result

    wrap_function_wrapper(
        wrapped_module_name,
        wrapped_function_name,
        _instrumented_lambda_handler_call,
    )


class AwsLambdaInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments Lambda Handlers on AWS Lambda.

        See more:
        https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/instrumentation/aws-lambda.md#instrumenting-aws-lambda

        Args:
            **kwargs: Optional arguments
                ``tracer_provider``: a TracerProvider, defaults to global
                ``meter_provider``: a MeterProvider, defaults to global
                ``event_context_extractor``: a method which takes the Lambda
                    Event as input and extracts an OTel Context from it. By default,
                    the context is extracted from the HTTP headers of an API Gateway
                    request.
                ``use_aws_context_propagation``: whether to use the AWS context propagation
                    to populate the parent context. When set to true, the spans
                    from the lambda runtime will not be added as span link to the
                    span of the lambda invocation.
                    Defaults to False.
        """
        _instrument(**kwargs)
        """
        lambda_handler = os.environ.get(ORIG_HANDLER, os.environ.get(_HANDLER))
        # pylint: disable=attribute-defined-outside-init
        (
            self._wrapped_module_name,
            self._wrapped_function_name,
        ) = lambda_handler.rsplit(".", 1)

        flush_timeout_env = os.environ.get(
            OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT, None
        )
        flush_timeout = 30000
        try:
            if flush_timeout_env is not None:
                flush_timeout = int(flush_timeout_env)
        except ValueError:
            logger.warning(
                "Could not convert OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT value %s to int",
                flush_timeout_env,
            )

        _instrument(
            self._wrapped_module_name,
            self._wrapped_function_name,
            flush_timeout,
            event_context_extractor=kwargs.get(
                "event_context_extractor", _default_event_context_extractor
            ),
            tracer_provider=kwargs.get("tracer_provider"),
            meter_provider=kwargs.get("meter_provider"),
            use_aws_context_propagation=kwargs.get(
                "use_aws_context_propagation",
                os.environ.get(OTEL_LAMBDA_USE_AWS_CONTEXT_PROPAGATION, "False").lower()
                in ("true", "1", "t"),
            ),
        )

    def _uninstrument(self, **kwargs):
        unwrap(
            import_module(self._wrapped_module_name),
            self._wrapped_function_name,
        )
