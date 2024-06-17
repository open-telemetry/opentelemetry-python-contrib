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
from typing import Any, Callable, Collection, Dict, List, Optional, Tuple, cast
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
    Span,
    SpanKind,
    TracerProvider,
    get_tracer,
    get_tracer_provider,
)
from opentelemetry.trace.propagation import get_current_span
from opentelemetry.trace.status import Status, StatusCode

logger = logging.getLogger(__name__)

_HANDLER = "_HANDLER"
_X_AMZN_TRACE_ID = "_X_AMZN_TRACE_ID"
ORIG_HANDLER = "ORIG_HANDLER"
OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT = (
    "OTEL_INSTRUMENTATION_AWS_LAMBDA_FLUSH_TIMEOUT"
)
OTEL_LAMBDA_DISABLE_AWS_CONTEXT_PROPAGATION = (
    "OTEL_LAMBDA_DISABLE_AWS_CONTEXT_PROPAGATION"
)
CONSUMER_EVENT_SOURCES = {"aws:sqs", "aws:s3", "aws:sns", "aws:dynamodb"}

LambdaEvent = Dict[str, Any]


class FlushableMeterProvider(MeterProvider):
    """
    Interface for a MeterProvider that can be flushed.
    """

    def force_flush(self, timeout: int) -> None:
        """
        Force flush all meter data.

        Args:
            timeout (int): The maximum amount of time to wait for the flush to complete,
                in milliseconds.

        Returns:
            None
        """


class FlushableTracerProvider(TracerProvider):
    """
    Interface for a TracerProvider that can be flushed.
    """

    def force_flush(self, timeout: int) -> None:
        """
        Force flush all meter data.

        Args:
            timeout (int): The maximum amount of time to wait for the flush to complete,
                in milliseconds.

        Returns:
            None
        """


def provider_warning(provider_type: str):
    """
    Log a warning that the provider is missing the `force_flush` method.

    Args:
        provider_type: Provider type to include in the warning message.

    Returns: A function that mimics the `force_flush` method, that will log a warning.
    """

    return lambda timeout: logger.warning(
        "%s was missing `force_flush` method. "
        "This is necessary in case of a Lambda freeze and would exist in the "
        "OTel SDK implementation.",
        provider_type,
    )


def determine_tracer_provider(
    tracer_provider_override: Optional[Any],
) -> FlushableTracerProvider:
    """
    Determine the TracerProvider to use for the instrumentation.

    The TracerProvider must have a `force_flush` method to be used in the instrumentation.
    If the TracerProvider does not have a `force_flush` method,
    a dummy `force_flush` method is added that logs a warning.

    Args:
        tracer_provider_override: Optional TracerProvider to use for the instrumentation.

    Returns: TracerProvider that is flushable.
    """

    if not isinstance(tracer_provider_override, TracerProvider):
        tracer_provider = get_tracer_provider()
    else:
        tracer_provider = tracer_provider_override

    if not hasattr(tracer_provider, "force_flush"):
        tracer_provider.force_flush = provider_warning(
            provider_type="TracerProvider"
        )

    return cast(FlushableTracerProvider, tracer_provider)


def determine_meter_provider(
    meter_provider_override: Optional[Any],
) -> FlushableMeterProvider:
    """
    Determine the MeterProvider to use for the instrumentation.

    The MeterProvider must have a `force_flush` method to be used in the instrumentation.
    If the MeterProvider does not have a `force_flush` method, a dummy `force_flush` method is added that logs a warning.

    Args:
        meter_provider_override: Optional MeterProvider to use for the instrumentation.

    Returns: MeterProvider that is flushable.
    """

    if not isinstance(meter_provider_override, MeterProvider):
        meter_provider = get_meter_provider()
    else:
        meter_provider = meter_provider_override

    if not hasattr(meter_provider, "force_flush"):
        meter_provider.force_flush = provider_warning(
            provider_type="MeterProvider"
        )

    return cast(FlushableMeterProvider, meter_provider)


def _handle_multi_value_headers_for_request(
    event: LambdaEvent,
) -> Dict[str, str]:
    """
    Process multi-value headers for a Lambda event.

    Args:
        event: Lambda event object.

    Returns: Headers for the Lambda event.
    """

    headers = event.get("headers", {}) or {}
    headers = {k.lower(): v for k, v in headers.items()}

    if event.get("multiValueHeaders"):
        headers.update(
            {
                k.lower(): ", ".join(v) if isinstance(v, list) else ""
                for k, v in event.get("multiValueHeaders", {}).items()
            }
        )

    return headers


class EventWrapper:
    """
    General purpose wrapper for Lambda events.
    """

    # This class is intended to be subclassed, so it has methods that are not, or partially implemented.
    # Keeping the signatures consistent for the subclasses to implement.
    # pylint:disable=R0201

    def __init__(self, event, context):
        self._event = event
        self._context = context

    @property
    def headers(self) -> dict:
        """
        Determine the headers for the event.

        Returns: Headers for the event.
        """

        if self._event and "headers" in self._event:
            return self._event["headers"]

        return {}

    @property
    def span_kind(self) -> SpanKind:
        """
        Determine the SpanKind for the event.

        Returns: SpanKind
        """

        return SpanKind.SERVER

    def set_pre_execution_span_attributes(self, span: Span, context) -> Span:
        """
        Set the span attributes before the Lambda function has executed.

        Args:
            span: Span to set attributes on.
            context: Lambda context object.

        Returns: The span with the attributes set.
        """

        if span.is_recording():
            # NOTE: The specs mention an exception here, allowing the
            # `SpanAttributes.CLOUD_RESOURCE_ID` attribute to be set as a span
            # attribute instead of a resource attribute.
            #
            # See more:
            # https://github.com/open-telemetry/semantic-conventions/blob/main/docs/faas/aws-lambda.md#resource-detector
            span.set_attribute(
                SpanAttributes.CLOUD_RESOURCE_ID,
                context.invoked_function_arn,
            )
            span.set_attribute(
                SpanAttributes.FAAS_INVOCATION_ID,
                context.aws_request_id,
            )

            # NOTE: `cloud.account.id` can be parsed from the ARN as the fifth item when splitting on `:`
            #
            # See more:
            # https://github.com/open-telemetry/semantic-conventions/blob/main/docs/faas/aws-lambda.md#all-triggers
            span.set_attribute(
                ResourceAttributes.CLOUD_ACCOUNT_ID,
                context.invoked_function_arn.split(":")[4],
            )

        return span

    def set_post_execution_span_attributes(
        self, span: Span, context, result: Any
    ) -> Span:
        """
        Set the span attributes after the Lambda function has executed.

        Args:
            span: Span to set attributes on.
            context: Lambda context object.
            result: Execution result of the Lambda function.

        Returns: The span with the attributes set.
        """

        _ = result
        return span


class ALBWrapper(EventWrapper):
    @property
    def headers(self) -> dict:
        """
        Determine the headers for the Application Load Balancer event.

        Returns: Headers for the Application Load Balancer event.
        """

        # This approach was adapted from the Mangum project:
        # https://github.com/jordaneremieff/mangum
        headers: List[Tuple[bytes, bytes]] = []

        if "multiValueHeaders" in self._event:
            for key, value in self._event["multiValueHeaders"].items():
                for inner_v in value:
                    headers.append((key.lower().encode(), inner_v.encode()))
        else:
            for key, value in self._event["headers"].items():
                headers.append((key.lower().encode(), value.encode()))

        # Unique headers. If there are duplicates, it will use the last defined.
        uq_headers = {k.decode(): v.decode() for k, v in headers}

        return uq_headers

    def set_post_execution_span_attributes(
        self, span: Span, context, result: Any
    ) -> Span:
        """
        Set the span attributes after the Lambda function has executed.

        Args:
            span: Span to set attributes on.
            context: Lambda context object.
            result: Execution result of the Lambda function.

        Returns: The span with the attributes set.
        """

        span.set_attribute(SpanAttributes.FAAS_TRIGGER, "http")

        if "httpMethod" in self._event:
            span.set_attribute(
                SpanAttributes.HTTP_METHOD,
                self._event["httpMethod"],
            )

        if self.headers:
            if "user-agent" in self.headers:
                span.set_attribute(
                    SpanAttributes.HTTP_USER_AGENT,
                    self.headers["user-agent"],
                )

            if "x-forwarded-proto" in self.headers:
                span.set_attribute(
                    SpanAttributes.HTTP_SCHEME,
                    self.headers["x-forwarded-proto"],
                )
            if "host" in self.headers:
                span.set_attribute(
                    SpanAttributes.NET_HOST_NAME,
                    self.headers["host"],
                )

        if "path" in self._event:
            span.set_attribute(SpanAttributes.HTTP_ROUTE, self._event["path"])

            if self._event.get("queryStringParameters"):
                span.set_attribute(
                    SpanAttributes.HTTP_TARGET,
                    f"{self._event['path']}?{urlencode(self._event['queryStringParameters'])}",
                )
            else:
                span.set_attribute(
                    SpanAttributes.HTTP_TARGET, self._event["path"]
                )

        return span


class BaseAPIGatewayWrapper(EventWrapper):
    def _set_api_gateway_v1_attributes(self, span: Span) -> Span:
        """
        Set the span attributes for API Gateway v1 events.

        Args:
            span: Span to set attributes on.

        Returns: The span with the attributes set.
        """

        span.set_attribute(
            SpanAttributes.HTTP_METHOD, self._event.get("httpMethod")
        )

        if self._event.get("headers"):
            if "User-Agent" in self._event["headers"]:
                span.set_attribute(
                    SpanAttributes.HTTP_USER_AGENT,
                    self._event["headers"]["User-Agent"],
                )
            if "X-Forwarded-Proto" in self._event["headers"]:
                span.set_attribute(
                    SpanAttributes.HTTP_SCHEME,
                    self._event["headers"]["X-Forwarded-Proto"],
                )
            if "Host" in self._event["headers"]:
                span.set_attribute(
                    SpanAttributes.NET_HOST_NAME,
                    self._event["headers"]["Host"],
                )

        if "resource" in self._event:
            span.set_attribute(
                SpanAttributes.HTTP_ROUTE, self._event["resource"]
            )

            if self._event.get("queryStringParameters"):
                span.set_attribute(
                    SpanAttributes.HTTP_TARGET,
                    f"{self._event['resource']}?{urlencode(self._event['queryStringParameters'])}",
                )
            else:
                span.set_attribute(
                    SpanAttributes.HTTP_TARGET, self._event["resource"]
                )

        return span


class APIGatewayHTTPWrapper(BaseAPIGatewayWrapper):
    @property
    def event_version(self) -> str:
        """
        Determine the version of the API Gateway event.

        Returns: The version of the API Gateway event.
        """

        return self._event["version"]

    @property
    def headers(self) -> dict:
        """
        Determine the headers for the API Gateway HTTP event.

        Returns: Headers for the API Gateway HTTP event.
        """

        # API Gateway v2
        if self.event_version == "2.0":
            return {
                k.lower(): v for k, v in self._event.get("headers", {}).items()
            }

        # API Gateway v1
        return _handle_multi_value_headers_for_request(self._event)

    def _set_api_gateway_v2_attributes(self, span: Span) -> Span:
        """
        Set the span attributes for API Gateway v2 events.

        Args:
            span: Span to set attributes on.

        Returns: The span with the attributes set.
        """

        if "domainName" in self._event["requestContext"]:
            span.set_attribute(
                SpanAttributes.NET_HOST_NAME,
                self._event["requestContext"]["domainName"],
            )

        if self._event["requestContext"].get("http"):
            if "method" in self._event["requestContext"]["http"]:
                span.set_attribute(
                    SpanAttributes.HTTP_METHOD,
                    self._event["requestContext"]["http"]["method"],
                )
            if "userAgent" in self._event["requestContext"]["http"]:
                span.set_attribute(
                    SpanAttributes.HTTP_USER_AGENT,
                    self._event["requestContext"]["http"]["userAgent"],
                )
            if "path" in self._event["requestContext"]["http"]:
                span.set_attribute(
                    SpanAttributes.HTTP_ROUTE,
                    self._event["requestContext"]["http"]["path"],
                )
                if self._event.get("rawQueryString"):
                    span.set_attribute(
                        SpanAttributes.HTTP_TARGET,
                        f"{self._event['requestContext']['http']['path']}?{self._event['rawQueryString']}",
                    )
                else:
                    span.set_attribute(
                        SpanAttributes.HTTP_TARGET,
                        self._event["requestContext"]["http"]["path"],
                    )

        return span

    def set_pre_execution_span_attributes(self, span, context) -> Span:
        """
        Set the span attributes before the Lambda function has executed.

        Args:
            span: Span to set attributes on.
            context: Lambda context object.

        Returns: The span with the attributes set.
        """

        super().set_pre_execution_span_attributes(span=span, context=context)
        span.set_attribute(SpanAttributes.FAAS_TRIGGER, "http")

        if self.event_version == "2.0":
            return self._set_api_gateway_v2_attributes(span)

        return self._set_api_gateway_v1_attributes(span)

    def set_post_execution_span_attributes(
        self, span: Span, context, result: Any
    ) -> Span:
        """
        Set the span attributes after the Lambda function has executed.

        Args:
            span: Span to set attributes on.
            context: Lambda context object.
            result: Execution result of the Lambda function.

        Returns: The span with the attributes set.
        """

        if isinstance(result, dict) and result.get("statusCode"):
            span.set_attribute(
                SpanAttributes.HTTP_STATUS_CODE,
                result.get("statusCode"),
            )

        return span


class APIGatewayProxyWrapper(BaseAPIGatewayWrapper):
    """
    Wrapper for API Gateway Proxy event.
    """

    @property
    def headers(self) -> dict:
        """
        Determine the headers for the API Gateway Proxy event.

        Returns: Headers for the API Gateway Proxy event.
        """

        return _handle_multi_value_headers_for_request(self._event)

    def set_pre_execution_span_attributes(self, span: Span, context) -> Span:
        """
        Set the span attributes before the Lambda function has executed.

        Args:
            span: Span to set attributes on.
            context: Lambda context object.

        Returns: The span with the attributes set.
        """

        super().set_pre_execution_span_attributes(span=span, context=context)
        span.set_attribute(SpanAttributes.FAAS_TRIGGER, "http")
        return self._set_api_gateway_v1_attributes(span)

    def set_post_execution_span_attributes(
        self, span: Span, context, result: Any
    ) -> Span:
        """
        Set the span attributes after the Lambda function has executed.

        Args:
            span: Span to set attributes on.
            context: Lambda context object.
            result: Execution result of the Lambda function.

        Returns: The span with the attributes set.
        """

        if isinstance(result, dict) and result.get("statusCode"):
            span.set_attribute(
                SpanAttributes.HTTP_STATUS_CODE,
                result.get("statusCode"),
            )

        return span


class ConsumerSource(EventWrapper):
    """
    General purpose wrapper for events that should be marked as a consumer span.
    """

    @property
    def span_kind(self):
        """
        Determine the SpanKing for the event.

        Returns: SpanKind.CONSUMER
        """

        return SpanKind.CONSUMER


def get_event_wrapper(event: LambdaEvent, context: Any) -> EventWrapper:
    """
    There isn't a consistent interface for the event object.

    Determine the event source and place it in a wrapper that can be used to extract the trace context,
    and relevant span attributes.

    Args:
        event: The Lambda event object.
        context: The Lambda context object.

    Returns: An EventWrapper that can be used to extract the trace context and span attributes.
    """

    default_wrapper = EventWrapper(event=event, context=context)

    # The logic behind this flow was adapted from work done by the Mangum project:
    # https://github.com/jordaneremieff/mangum
    # To reduce cognitive load, preserving if/elif structure.
    # pylint:disable=R1705
    if not event:
        return default_wrapper
    elif "requestContext" in event and "elb" in event["requestContext"]:
        return ALBWrapper(event=event, context=context)
    elif "version" in event and "requestContext" in event:
        return APIGatewayHTTPWrapper(event=event, context=context)
    elif "resource" in event and "requestContext" in event:
        return APIGatewayProxyWrapper(event=event, context=context)
    elif "Records" in event and len(event["Records"]) > 0:
        # There appears to be inconsistency in the event source key for different event types.
        if (
            "eventSource" in event["Records"][0]
            and event["Records"][0]["eventSource"] in CONSUMER_EVENT_SOURCES
        ) or (
            "EventSource" in event["Records"][0]
            and event["Records"][0]["EventSource"] in CONSUMER_EVENT_SOURCES
        ):
            return ConsumerSource(event=event, context=context)

    return default_wrapper


def _determine_parent_context(
    event: EventWrapper,
    event_context_extractor: Callable[[Any], Context],
    disable_aws_context_propagation: bool,
) -> Context:
    """Determine the parent context for the current Lambda invocation.

    See more:    https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/trace/semantic_conventions/instrumentation/aws-lambda.md#determining-the-parent-of-a-span
    Args:        lambda_event: user-defined, so it could be anything, but this            method counts it being a map with a 'headers' key        event_context_extractor: a method which takes the Lambda            Event as input and extracts an OTel Context from it. By default,            the context is extracted from the HTTP headers of an API Gateway            request.        disable_aws_context_propagation: By default, this instrumentation            will try to read the context from the `_X_AMZN_TRACE_ID` environment            variable set by Lambda, set this to `True` to disable this behavior.    Returns:        A Context with configuration found in the carrier.
    """

    parent_context = None

    if not disable_aws_context_propagation:
        xray_env_var = os.environ.get(_X_AMZN_TRACE_ID)

        if xray_env_var:
            parent_context = AwsXRayPropagator().extract(
                {TRACE_HEADER_KEY: xray_env_var}
            )

    if (
        parent_context
        and get_current_span(parent_context)
        .get_span_context()
        .trace_flags.sampled
    ):
        return parent_context

    parent_context = event_context_extractor(event)

    return parent_context


def flush(
    tracer_provider: FlushableTracerProvider,
    meter_provider: FlushableMeterProvider,
) -> None:
    """
    Flushes the tracer and meter providers.

    Args:
        tracer_provider: Tracer provider to flush.
        meter_provider: Meter provider to flush.

    Returns: None
    """

    flush_timeout = determine_flush_timeout()

    now = time.time()

    try:
        # NOTE: `force_flush` before function quit in case of Lambda freeze.
        tracer_provider.force_flush(flush_timeout)
    except Exception:  # pylint: disable=broad-except
        logger.exception("TracerProvider failed to flush traces")

    rem = int(flush_timeout - (time.time() - now) * 1000)
    if rem > 0:
        try:
            # NOTE: `force_flush` before function quit in case of Lambda freeze.
            meter_provider.force_flush(rem)
        except Exception:  # pylint: disable=broad-except
            logger.exception("MeterProvider failed to flush metrics")


def _instrument(
    wrapped_module_name,
    wrapped_function_name,
    event_context_extractor: Callable[[Any], Context],
    disable_aws_context_propagation: bool,
    tracer_provider: FlushableTracerProvider,
    meter_provider: FlushableMeterProvider,
):
    def _instrumented_lambda_handler_call(  # noqa pylint: disable=too-many-branches
        call_wrapped, instance, args, kwargs
    ):
        _ = instance

        orig_handler_name = ".".join(
            [wrapped_module_name, wrapped_function_name]
        )

        lambda_event = args[0]
        lambda_context = args[1]
        event_wrapper = get_event_wrapper(
            event=lambda_event, context=lambda_context
        )

        parent_context = _determine_parent_context(
            event_wrapper,
            event_context_extractor,
            disable_aws_context_propagation,
        )

        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        with tracer.start_as_current_span(
            name=orig_handler_name,
            context=parent_context,
            kind=event_wrapper.span_kind,
        ) as span:
            event_wrapper.set_pre_execution_span_attributes(
                span=span, context=lambda_context
            )

            exception = None
            result = None
            try:
                result = call_wrapped(*args, **kwargs)
            except Exception as exc:  # pylint: disable=W0703
                exception = exc
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(exception)

            event_wrapper.set_post_execution_span_attributes(
                span=span, context=lambda_context, result=result
            )

        flush(
            meter_provider=meter_provider,
            tracer_provider=tracer_provider,
        )

        if exception is not None:
            raise exception.with_traceback(exception.__traceback__)

        return result

    wrap_function_wrapper(
        wrapped_module_name,
        wrapped_function_name,
        _instrumented_lambda_handler_call,
    )


def determine_flush_timeout() -> int:
    """
    Determine the flush timeout for the Lambda function.

    Returns: Flush timeout in milliseconds
    """

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

    return flush_timeout


def is_aws_context_propagation_disabled(
    disable_aws_context_propagation_override: Any,
) -> bool:
    """
    Determine if AWS context propagation should be disabled.

    Propagation can be disabled by setting the `OTEL_LAMBDA_DISABLE_AWS_CONTEXT_PROPAGATION` environment variable to:
    `true`, `1`, or `t`.
    Or, by passing `True` to the `disable_aws_context_propagation` parameter in the `instrument` method.

    Args:
        disable_aws_context_propagation_override: Flag indicating whether AWS context propagation should be disabled.

    Returns: True if AWS context propagation should be disabled, False otherwise.
    """

    if not isinstance(disable_aws_context_propagation_override, bool):
        logger.warning(
            "disable_aws_context_propagation must be a boolean, got %s",
            type(disable_aws_context_propagation_override),
        )
        disable_aws_context_propagation_override = False

    disable_from_env = False

    # If the override is set, use it, otherwise check the environment variable.
    if not disable_aws_context_propagation_override:
        env_value = (
            os.getenv(OTEL_LAMBDA_DISABLE_AWS_CONTEXT_PROPAGATION, "False")
            .strip()
            .lower()
        )
        disable_from_env = env_value in ("true", "1", "t")

    return disable_aws_context_propagation_override or disable_from_env


def determine_context_extractor(
    context_extractor_override: Optional[Callable],
) -> Callable:
    """
    Determine the context extractor to use for the Lambda instrumentation.
    The context extract should accept an EventWrapper and return an OTel Context.

    Args:
        context_extractor_override: Optional context extractor to use.

    Returns: A context extractor function.
    """

    if callable(context_extractor_override):
        return context_extractor_override

    return lambda event: get_global_textmap().extract(event.headers)


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
                ``disable_aws_context_propagation``: By default, this instrumentation
                    will try to read the context from the `_X_AMZN_TRACE_ID` environment
                    variable set by Lambda, set this to `True` to disable this behavior.
        """

        lambda_handler = os.environ.get(ORIG_HANDLER, os.environ.get(_HANDLER))
        # pylint: disable=attribute-defined-outside-init
        (
            self._wrapped_module_name,
            self._wrapped_function_name,
        ) = lambda_handler.rsplit(".", 1)

        _instrument(
            self._wrapped_module_name,
            self._wrapped_function_name,
            event_context_extractor=determine_context_extractor(
                context_extractor_override=kwargs.get(
                    "event_context_extractor"
                )
            ),
            disable_aws_context_propagation=is_aws_context_propagation_disabled(
                disable_aws_context_propagation_override=kwargs.get(
                    "disable_aws_context_propagation", False
                )
            ),
            meter_provider=determine_meter_provider(
                meter_provider_override=kwargs.get("meter_provider")
            ),
            tracer_provider=determine_tracer_provider(
                tracer_provider_override=kwargs.get("tracer_provider")
            ),
        )

    def _uninstrument(self, **kwargs):
        unwrap(
            import_module(self._wrapped_module_name),
            self._wrapped_function_name,
        )
