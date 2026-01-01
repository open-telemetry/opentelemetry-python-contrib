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
OpenTelemetry Mistral AI Instrumentation
=========================================

Instrumentation for the Mistral AI Python SDK.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.mistralai import MistralAIInstrumentor
    from mistralai import Mistral

    # Enable instrumentation
    MistralAIInstrumentor().instrument()

    # Use Mistral client as normal
    client = Mistral(api_key="your-api-key")
    response = client.chat.complete(
        model="mistral-small-latest",
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

from opentelemetry.instrumentation.mistralai.package import _instruments
from opentelemetry.instrumentation.mistralai.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

WRAPPED_METHODS = [
    {
        "module": "mistralai.chat",
        "object": "Chat",
        "method": "complete",
        "wrapper_factory": "create_chat_complete_wrapper",
    },
    {
        "module": "mistralai.chat",
        "object": "Chat",
        "method": "stream",
        "wrapper_factory": "create_chat_stream_wrapper",
    },
    {
        "module": "mistralai.embeddings",
        "object": "Embeddings",
        "method": "create",
        "wrapper_factory": "create_embeddings_wrapper",
    },
    {
        "module": "mistralai.chat",
        "object": "Chat",
        "method": "complete_async",
        "wrapper_factory": "create_async_chat_complete_wrapper",
    },
]


class MistralAIInstrumentor(BaseInstrumentor):
    """An instrumentor for Mistral AI's Python SDK.

    This instrumentor will automatically trace Mistral AI API calls.
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
        """Enable Mistral AI instrumentation."""
        from opentelemetry._logs import get_logger
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.mistralai import patch
        from opentelemetry.instrumentation.mistralai.utils import Config

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
            module = method_info["module"]
            obj = method_info["object"]
            method = method_info["method"]
            wrapper_factory = method_info["wrapper_factory"]

            try:
                wrapper_func = getattr(patch, wrapper_factory)
                wrapper = wrapper_func(tracer, event_logger)

                wrap_function_wrapper(module, f"{obj}.{method}", wrapper)

                logger.debug("Successfully wrapped %s.%s.%s", module, obj, method)
            except Exception as e:
                logger.debug("Failed to wrap %s.%s.%s: %s", module, obj, method, e)

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Mistral AI instrumentation."""
        for method_info in WRAPPED_METHODS:
            module = method_info["module"]
            obj = method_info["object"]
            method = method_info["method"]
            try:
                import importlib

                mod = importlib.import_module(module)
                cls = getattr(mod, obj)
                unwrap(cls, method)
            except Exception:
                pass
