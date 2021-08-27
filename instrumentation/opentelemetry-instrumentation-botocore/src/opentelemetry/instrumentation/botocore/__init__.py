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

"""
Instrument `Botocore`_ to trace service requests.

There are two options for instrumenting code. The first option is to use the
``opentelemetry-instrument`` executable which will automatically
instrument your Botocore client. The second is to programmatically enable
instrumentation via the following code:

.. _Botocore: https://pypi.org/project/botocore/

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
    import botocore


    # Instrument Botocore
    BotocoreInstrumentor().instrument()

    # This will create a span with Botocore-specific attributes
    session = botocore.session.get_session()
    session.set_credentials(
        access_key="access-key", secret_key="secret-key"
    )
    ec2 = self.session.create_client("ec2", region_name="us-west-2")
    ec2.describe_instances()

API
---
"""

import json
import logging
from typing import Callable, Collection, Optional

from botocore.client import BaseClient
from botocore.endpoint import Endpoint
from botocore.exceptions import ClientError
from wrapt import wrap_function_wrapper

from opentelemetry import context as context_api
from opentelemetry.instrumentation.botocore.extensions import find_extension
from opentelemetry.instrumentation.botocore.extensions.types import (
    AwsSdkCallContext,
    AwsSdkExtension,
)
from opentelemetry.instrumentation.botocore.package import _instruments
from opentelemetry.instrumentation.botocore.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import (
    _SUPPRESS_INSTRUMENTATION_KEY,
    unwrap,
)
from opentelemetry.propagate import inject
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import SpanKind, get_tracer
from opentelemetry.trace.span import Span

logger = logging.getLogger(__name__)

# A key to a context variable to avoid creating duplicate spans when instrumenting
# both botocore.client and urllib3.connectionpool.HTTPConnectionPool.urlopen since
# botocore calls urlopen
_SUPPRESS_HTTP_INSTRUMENTATION_KEY = context_api.create_key(
    "suppress_http_instrumentation"
)


# pylint: disable=unused-argument
def _patched_endpoint_prepare_request(wrapped, instance, args, kwargs):
    request = args[0]
    headers = request.headers
    inject(headers)
    return wrapped(*args, **kwargs)


class BotocoreInstrumentor(BaseInstrumentor):
    """An instrumentor for Botocore.

    See `BaseInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):

        # pylint: disable=attribute-defined-outside-init
        self._tracer = get_tracer(
            __name__, __version__, kwargs.get("tracer_provider")
        )

        wrap_function_wrapper(
            "botocore.client",
            "BaseClient._make_api_call",
            self._patched_api_call,
        )

        wrap_function_wrapper(
            "botocore.endpoint",
            "Endpoint.prepare_request",
            _patched_endpoint_prepare_request,
        )

    def _uninstrument(self, **kwargs):
        unwrap(BaseClient, "_make_api_call")
        unwrap(Endpoint, "prepare_request")

    def _patched_api_call(self, original_func, instance, args, kwargs):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return original_func(*args, **kwargs)

        call_context = _determine_call_context(instance, args)
        if call_context is None:
            return original_func(*args, **kwargs)

        extension = find_extension(call_context)
        if not extension.should_trace_service_call():
            return original_func(*args, **kwargs)

        attributes = {
            SpanAttributes.RPC_SYSTEM: "aws-api",
            SpanAttributes.RPC_SERVICE: call_context.service_id,
            SpanAttributes.RPC_METHOD: call_context.operation,
            # TODO: update when semantic conventions exist
            "aws.region": call_context.region,
        }

        _safe_invoke(extension.extract_attributes, attributes)

        with self._tracer.start_as_current_span(
            call_context.span_name,
            kind=call_context.span_kind,
            attributes=attributes,
        ) as span:
            _safe_invoke(extension.before_service_call, span)

            token = context_api.attach(
                context_api.set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True)
            )

            try:
                result = original_func(*args, **kwargs)
            except ClientError as error:
                error_result = getattr(error, "response", None)
                _apply_response_attributes(span, error_result)
                _safe_invoke(extension.on_error, span, error)
                raise
            else:
                _apply_response_attributes(span, result)
                _safe_invoke(extension.on_success, span, result)
            finally:
                context_api.detach(token)
                _safe_invoke(extension.after_service_call)
            return result


def _apply_response_attributes(span: Span, result):
    if result is None or not span.is_recording():
        return

    metadata = result.get("ResponseMetadata")
    if metadata is None:
        return

    request_id = metadata.get("RequestId")
    if request_id is None:
        headers = metadata.get("HTTPHeaders")
        if headers is not None:
            request_id = (
                headers.get("x-amzn-RequestId")
                or headers.get("x-amz-request-id")
                or headers.get("x-amz-id-2")
            )
    if request_id:
        # TODO: update when semantic conventions exist
        span.set_attribute("aws.request_id", request_id)

    retry_attempts = metadata.get("RetryAttempts")
    if retry_attempts is not None:
        # TODO: update when semantic conventinos exists
        span.set_attribute("retry_attempts", retry_attempts)

    status_code = metadata.get("HTTPStatusCode")
    if status_code is not None:
        span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, status_code)


def _determine_call_context(
    client: BaseClient, args
) -> Optional[AwsSdkCallContext]:
    try:
        operation = args[0]
        params = args[1]
        call_context = AwsSdkCallContext(client, operation, params)

        logger.debug(
            "AWS SDK invocation: %s %s",
            call_context.service,
            call_context.operation,
        )

        return call_context
    except Exception as ex:  # pylint:disable=broad-except
        logger.warning("Error when initializing call context", exc_info=ex)
        return None


def _safe_invoke(function: Callable, *args):
    function_name = "<unknown>"
    try:
        function_name = function.__name__
        function(*args)
    except Exception as ex:  # pylint:disable=broad-except
        logger.warning(
            "Error when invoking extension function '%s'",
            function_name,
            exc_info=ex,
        )
