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
OpenTelemetry Replicate Instrumentation
=======================================

Instrumentation for the Replicate Python SDK.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.replicate import ReplicateInstrumentor
    import replicate

    # Enable instrumentation
    ReplicateInstrumentor().instrument()

    # Use Replicate client normally
    output = replicate.run(
        "stability-ai/stable-diffusion:db21e45d3f7023abc2a46ee38a23973f6dce16bb082a930b0c49861f96d1e5bf",
        input={"prompt": "an astronaut riding a horse"}
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

from opentelemetry.instrumentation.replicate.package import _instruments
from opentelemetry.instrumentation.replicate.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas

logger = logging.getLogger(__name__)

WRAPPED_METHODS = [
    {
        "module": "replicate",
        "method": "run",
        "wrapper_factory": "create_run_wrapper",
    },
    {
        "module": "replicate",
        "method": "stream",
        "wrapper_factory": "create_stream_wrapper",
    },
    {
        "module": "replicate.prediction",
        "object": "Predictions",
        "method": "create",
        "wrapper_factory": "create_predictions_create_wrapper",
    },
]


class ReplicateInstrumentor(BaseInstrumentor):
    """An instrumentor for Replicate's Python SDK.

    This instrumentor will automatically trace Replicate API calls.
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
        """Enable Replicate instrumentation."""
        from opentelemetry._logs import get_logger
        from opentelemetry.trace import get_tracer

        from opentelemetry.instrumentation.replicate import patch
        from opentelemetry.instrumentation.replicate.utils import Config

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
            method = method_info["method"]
            wrapper_factory = method_info["wrapper_factory"]

            try:
                wrapper_func = getattr(patch, wrapper_factory)
                wrapper = wrapper_func(tracer, event_logger)

                if "object" in method_info:
                    wrap_function_wrapper(
                        module,
                        f"{method_info['object']}.{method}",
                        wrapper,
                    )
                else:
                    wrap_function_wrapper(module, method, wrapper)

                logger.debug("Successfully wrapped %s.%s", module, method)
            except Exception as e:
                logger.debug("Failed to wrap %s.%s: %s", module, method, e)

    def _uninstrument(self, **kwargs: Any) -> None:
        """Disable Replicate instrumentation."""
        import replicate

        for method_info in WRAPPED_METHODS:
            method = method_info["method"]
            try:
                if "object" in method_info:
                    import replicate.prediction

                    unwrap(replicate.prediction.Predictions, method)
                else:
                    unwrap(replicate, method)
            except Exception:
                pass
