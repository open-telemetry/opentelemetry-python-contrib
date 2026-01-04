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
OpenTelemetry Together AI Instrumentation
=========================================

Instrumentation for the Together AI Python SDK.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.together import TogetherInstrumentor
    import together

    # Enable instrumentation
    TogetherInstrumentor().instrument()

    # Use Together client normally
    client = together.Together(api_key="your-api-key")
    response = client.chat.completions.create(
        model="mistralai/Mixtral-8x7B-Instruct-v0.1",
        messages=[{"role": "user", "content": "Hello!"}]
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

from opentelemetry.instrumentation.together.package import _instruments
from opentelemetry.instrumentation.together.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

WRAPPED_METHODS = [
    {
        "package": "together.resources.chat.completions",
        "object": "ChatCompletions",
        "method": "create",
        "span_name": "together.chat",
    },
    {
        "package": "together.resources.completions",
        "object": "Completions",
        "method": "create",
        "span_name": "together.completion",
    },
]


class TogetherInstrumentor(BaseInstrumentor):
    """An instrumentor for Together AI's Python SDK.

    This instrumentor will automatically trace Together AI API calls.
    """

    def __init__(
        self,
        exception_logger: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        super().__init__()
        self._tracer = None
        self._event_logger = None
        self._exception_logger = exception_logger

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Together instrumentation."""
        from opentelemetry._logs import get_logger
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.together.patch import create_wrapper
        from opentelemetry.instrumentation.together.utils import Config

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

        for method_info in WRAPPED_METHODS:
            wrap_package = method_info["package"]
            wrap_object = method_info["object"]
            wrap_method = method_info["method"]
            span_name = method_info["span_name"]

            try:
                wrapper = create_wrapper(
                    tracer,
                    event_logger,
                    wrap_method,
                    span_name,
                )
                wrap_function_wrapper(
                    wrap_package,
                    f"{wrap_object}.{wrap_method}",
                    wrapper,
                )
                logger.debug(
                    "Successfully wrapped %s.%s.%s",
                    wrap_package,
                    wrap_object,
                    wrap_method,
                )
            except Exception as e:
                logger.debug(
                    "Failed to wrap %s.%s.%s: %s",
                    wrap_package,
                    wrap_object,
                    wrap_method,
                    e,
                )

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Together instrumentation."""
        for method_info in WRAPPED_METHODS:
            wrap_package = method_info["package"]
            wrap_object = method_info["object"]
            wrap_method = method_info["method"]
            try:
                unwrap(f"{wrap_package}.{wrap_object}", wrap_method)
            except Exception:
                pass
