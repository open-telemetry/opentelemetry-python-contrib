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
OpenTelemetry AWS SageMaker Instrumentation
============================================

Instrumentation for AWS SageMaker Runtime using boto3.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.sagemaker import SageMakerInstrumentor
    import boto3

    # Enable instrumentation
    SageMakerInstrumentor().instrument()

    # Use SageMaker Runtime client as normal
    client = boto3.client("sagemaker-runtime")
    response = client.invoke_endpoint(
        EndpointName="my-endpoint",
        Body=b'{"inputs": "Hello!"}',
        ContentType="application/json",
    )

Configuration
-------------

Message content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

API
---
"""

import logging
from typing import Any, Callable, Collection, Optional

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.sagemaker.package import _instruments
from opentelemetry.instrumentation.sagemaker.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)


class SageMakerInstrumentor(BaseInstrumentor):
    """An instrumentor for AWS SageMaker Runtime.

    This instrumentor will automatically trace SageMaker Runtime API calls.
    """

    def __init__(
        self,
        exception_logger: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        super().__init__()
        self._tracer = None
        self._event_logger = None
        self._exception_logger = exception_logger
        self._original_make_api_call = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable SageMaker instrumentation."""
        from opentelemetry._logs import get_logger
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.sagemaker import patch
        from opentelemetry.instrumentation.sagemaker.utils import Config

        if self._exception_logger:
            Config.exception_logger = self._exception_logger

        tracer_provider = kwargs.get("tracer_provider")
        logger_provider = kwargs.get("logger_provider")

        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        event_logger = get_logger(
            __name__,
            __version__,
            schema_url=Schemas.V1_28_0.value,
            logger_provider=logger_provider,
        )

        self._tracer = tracer
        self._event_logger = event_logger

        # Wrap boto3 SageMaker Runtime client methods
        try:
            import botocore.client

            invoke_endpoint_wrapper = patch.create_invoke_endpoint_wrapper(
                tracer, event_logger
            )
            invoke_endpoint_async_wrapper = patch.create_invoke_endpoint_async_wrapper(
                tracer, event_logger
            )
            invoke_stream_wrapper = patch.create_invoke_endpoint_with_response_stream_wrapper(
                tracer, event_logger
            )

            # Store original _make_api_call for uninstrumentation
            self._original_make_api_call = botocore.client.BaseClient._make_api_call

            original_make_api_call = botocore.client.BaseClient._make_api_call

            def patched_make_api_call(self, operation_name, api_params):
                # Only instrument sagemaker-runtime operations
                if hasattr(self, "_service_model"):
                    service_name = self._service_model.service_name
                    if service_name == "sagemaker-runtime":
                        if operation_name == "InvokeEndpoint":
                            return invoke_endpoint_wrapper(
                                lambda *args, **kwargs: original_make_api_call(
                                    self, operation_name, api_params
                                ),
                                self,
                                (),
                                api_params,
                            )
                        elif operation_name == "InvokeEndpointAsync":
                            return invoke_endpoint_async_wrapper(
                                lambda *args, **kwargs: original_make_api_call(
                                    self, operation_name, api_params
                                ),
                                self,
                                (),
                                api_params,
                            )
                        elif operation_name == "InvokeEndpointWithResponseStream":
                            return invoke_stream_wrapper(
                                lambda *args, **kwargs: original_make_api_call(
                                    self, operation_name, api_params
                                ),
                                self,
                                (),
                                api_params,
                            )

                return original_make_api_call(self, operation_name, api_params)

            botocore.client.BaseClient._make_api_call = patched_make_api_call

            logger.debug("Successfully instrumented SageMaker Runtime")
        except Exception as e:
            logger.debug("Failed to instrument SageMaker Runtime: %s", e)

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable SageMaker instrumentation."""
        try:
            import botocore.client

            if self._original_make_api_call:
                botocore.client.BaseClient._make_api_call = self._original_make_api_call
                self._original_make_api_call = None
        except Exception:
            pass
