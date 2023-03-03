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
Instrument `AioBotocore`_ to trace service requests.

There are two options for instrumenting code. The first option is to use the
``opentelemetry-instrument`` executable which will automatically
instrument your AioBotocore client. The second is to programmatically enable
instrumentation via the following code:

.. _AioBotocore: https://pypi.org/project/aiobotocore/

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.aiobotocore import AioBotocoreInstrumentor
    import aiobotocore.session


    # Instrument AioBotocore
    AioBotocoreInstrumentor().instrument()

    # This will create a span with AioBotocore-specific attributes
    session = aiobotocore.session.get_session()
    session.set_credentials(
        access_key="access-key", secret_key="secret-key"
    )
    with session.create_client("ec2", region_name="us-west-2") as ec2:
        await ec2.describe_instances()

API
---

The `instrument` method accepts the following keyword args:

tracer_provider (TracerProvider) - an optional tracer provider
request_hook (Callable) - a function with extra user-defined logic to be performed before performing the request
this function signature is:  def request_hook(span: Span, service_name: str, operation_name: str, api_params: dict) -> None
response_hook (Callable) - a function with extra user-defined logic to be performed after performing the request
this function signature is:  def request_hook(span: Span, service_name: str, operation_name: str, result: dict) -> None

for example:

.. code:: python

    from opentelemetry.instrumentation.aiobotocore import AioBotocoreInstrumentor
    import aiobotocore.session

    def request_hook(span, service_name, operation_name, api_params):
        # request hook logic

    def response_hook(span, service_name, operation_name, result):
        # response hook logic

    # Instrument AioBotocore with hooks
    AioBotocoreInstrumentor().instrument(request_hook=request_hook, response_hook=response_hook)

    # This will create a span with AioBotocore-specific attributes, including custom attributes added from the hooks
    session = aiobotocore.session.get_session()
    session.set_credentials(
        access_key="access-key", secret_key="secret-key"
    )
    with session.create_client("ec2", region_name="us-west-2") as ec2:
        await ec2.describe_instances()
"""

from typing import Collection

from aiobotocore.client import AioBaseClient
from aiobotocore.endpoint import AioEndpoint
from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.aiobotocore.package import _instruments
from opentelemetry.instrumentation.aiobotocore.version import __version__
from opentelemetry.instrumentation.botocore import (
    BotocoreInstrumentor,
    _patched_endpoint_prepare_request,
    _trace_api_call,
)
from opentelemetry.instrumentation.utils import unwrap


class AioBotocoreInstrumentor(BotocoreInstrumentor):
    """An instrumentor for AioBotocore.

    See `BotocoreInstrumentor`
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        self._init_instrument(__name__, __version__, **kwargs)

        wrap_function_wrapper(
            "aiobotocore.client",
            "AioBaseClient._make_api_call",
            self._patched_api_call,
        )

        wrap_function_wrapper(
            "aiobotocore.endpoint",
            "AioEndpoint.prepare_request",
            _patched_endpoint_prepare_request,
        )

    def _uninstrument(self, **kwargs):
        unwrap(AioBaseClient, "_make_api_call")
        unwrap(AioEndpoint, "prepare_request")

    async def _patched_api_call(self, original_func, instance, args, kwargs):
        with _trace_api_call(self, instance, args) as trace_context:
            if trace_context is None:
                return await original_func(*args, **kwargs)

            result = await original_func(*args, **kwargs)
            trace_context["result"] = result

            return result
