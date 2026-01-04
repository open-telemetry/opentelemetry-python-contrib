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
OpenTelemetry AWS Bedrock Instrumentation
==========================================

Instrumentation for AWS Bedrock Runtime using boto3.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.bedrock import BedrockInstrumentor
    import boto3
    import json

    # Enable instrumentation
    BedrockInstrumentor().instrument()

    # Use Bedrock Runtime client as normal
    client = boto3.client("bedrock-runtime")
    response = client.invoke_model(
        modelId="anthropic.claude-v2",
        body=json.dumps({
            "prompt": "Human: Hello!\\n\\nAssistant:",
            "max_tokens_to_sample": 100
        }),
        contentType="application/json",
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

from opentelemetry.instrumentation.bedrock.package import _instruments
from opentelemetry.instrumentation.bedrock.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)


class BedrockInstrumentor(BaseInstrumentor):
    """An instrumentor for AWS Bedrock Runtime.

    This instrumentor will automatically trace Bedrock Runtime API calls.
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
        """Enable Bedrock instrumentation."""
        from opentelemetry._logs import get_logger
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.bedrock import patch
        from opentelemetry.instrumentation.bedrock.utils import Config

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

        # Wrap boto3 Bedrock Runtime client methods
        try:
            import botocore.client

            invoke_model_wrapper = patch.create_invoke_model_wrapper(tracer, event_logger)
            converse_wrapper = patch.create_converse_wrapper(tracer, event_logger)
            converse_stream_wrapper = patch.create_converse_stream_wrapper(tracer, event_logger)

            # Store original _make_api_call for uninstrumentation
            self._original_make_api_call = botocore.client.BaseClient._make_api_call

            original_make_api_call = botocore.client.BaseClient._make_api_call

            def patched_make_api_call(self, operation_name, api_params):
                # Only instrument bedrock-runtime operations
                if hasattr(self, "_service_model"):
                    service_name = self._service_model.service_name
                    if service_name == "bedrock-runtime":
                        if operation_name == "InvokeModel":
                            return invoke_model_wrapper(
                                lambda *args, **kwargs: original_make_api_call(
                                    self, operation_name, api_params
                                ),
                                self,
                                (),
                                api_params,
                            )
                        elif operation_name == "Converse":
                            return converse_wrapper(
                                lambda *args, **kwargs: original_make_api_call(
                                    self, operation_name, api_params
                                ),
                                self,
                                (),
                                api_params,
                            )
                        elif operation_name == "ConverseStream":
                            return converse_stream_wrapper(
                                lambda *args, **kwargs: original_make_api_call(
                                    self, operation_name, api_params
                                ),
                                self,
                                (),
                                api_params,
                            )

                return original_make_api_call(self, operation_name, api_params)

            botocore.client.BaseClient._make_api_call = patched_make_api_call

            logger.debug("Successfully instrumented Bedrock Runtime")
        except Exception as e:
            logger.debug("Failed to instrument Bedrock Runtime: %s", e)

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Bedrock instrumentation."""
        try:
            import botocore.client

            if self._original_make_api_call:
                botocore.client.BaseClient._make_api_call = self._original_make_api_call
                self._original_make_api_call = None
        except Exception:
            pass
