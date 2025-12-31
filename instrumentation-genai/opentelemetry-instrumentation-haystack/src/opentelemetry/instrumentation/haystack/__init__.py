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
Haystack instrumentation for OpenTelemetry.

This instrumentation provides automatic tracing of Haystack pipeline executions,
including:
- Pipeline run operations (workflow level)
- OpenAI generator calls (completion and chat)

Haystack is a modern NLP framework for building production-ready LLM applications.
This instrumentation supports Haystack 2.0+.

Usage
-----
.. code:: python

    from opentelemetry.instrumentation.haystack import HaystackInstrumentor
    from haystack import Pipeline
    from haystack.components.generators import OpenAIGenerator

    HaystackInstrumentor().instrument()

    # Create a pipeline
    pipeline = Pipeline()
    pipeline.add_component("generator", OpenAIGenerator())

    # Run the pipeline
    result = pipeline.run({"generator": {"prompt": "What is AI?"}})

    HaystackInstrumentor().uninstrument()

API
---
"""

import logging
from typing import Any, Collection

from wrapt import wrap_function_wrapper  # type: ignore[import-untyped]

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.haystack.package import _instruments
from opentelemetry.instrumentation.haystack.patch import (
    wrap_openai_generator,
    wrap_pipeline,
)
from opentelemetry.instrumentation.haystack.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer

logger = logging.getLogger(__name__)

# Methods to wrap with their configurations
WRAPPED_METHODS = [
    {
        "package": "haystack.components.generators.openai",
        "object": "OpenAIGenerator",
        "method": "run",
        "wrapper": wrap_openai_generator,
    },
    {
        "package": "haystack.components.generators.chat.openai",
        "object": "OpenAIChatGenerator",
        "method": "run",
        "wrapper": wrap_openai_generator,
    },
    {
        "package": "haystack.core.pipeline.pipeline",
        "object": "Pipeline",
        "method": "run",
        "wrapper": wrap_pipeline,
    },
]


class HaystackInstrumentor(BaseInstrumentor):
    """OpenTelemetry instrumentor for Haystack.

    This instrumentor wraps Haystack's Pipeline and generator classes to capture
    telemetry for workflow executions.

    Features:
        - Automatic span creation for pipeline runs
        - OpenAI generator tracing with request/response capture
        - Support for both completion and chat generators
        - Content capture controlled by environment variable

    Example:
        >>> from opentelemetry.instrumentation.haystack import HaystackInstrumentor
        >>> instrumentor = HaystackInstrumentor()
        >>> instrumentor.instrument()
        >>> # Use Haystack as normal
        >>> instrumentor.uninstrument()

    Attributes:
        All spans use the `gen_ai.haystack.*` namespace for custom attributes,
        following OpenTelemetry semantic conventions.
    """

    def __init__(self) -> None:
        """Initialize the Haystack instrumentor."""
        super().__init__()

    def instrumentation_dependencies(self) -> Collection[str]:
        """Return the instrumented package dependencies."""
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        """Enable Haystack instrumentation.

        Args:
            **kwargs: Additional configuration options.
                - tracer_provider: Custom TracerProvider
        """
        tracer_provider = kwargs.get("tracer_provider")

        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        for wrapped_method in WRAPPED_METHODS:
            wrap_package = wrapped_method.get("package")
            wrap_object = wrapped_method.get("object")
            wrap_method = wrapped_method.get("method")
            wrapper = wrapped_method.get("wrapper")

            if wrap_package and wrap_method and wrapper:
                self._safe_wrap(
                    wrap_package,
                    f"{wrap_object}.{wrap_method}" if wrap_object else wrap_method,
                    wrapper(tracer, wrapped_method),
                )

    def _safe_wrap(
        self, module: str, name: str, wrapper: Any
    ) -> None:
        """Safely wrap a function, ignoring errors if module/function not found.

        This allows backwards compatibility with different Haystack versions.

        Args:
            module: The module path.
            name: The function/method name to wrap.
            wrapper: The wrapper function.
        """
        try:
            wrap_function_wrapper(module=module, name=name, wrapper=wrapper)
        except (ImportError, AttributeError, ModuleNotFoundError):
            logger.debug(
                "Could not wrap %s.%s - may not be available in this version",
                module,
                name,
            )

    def _uninstrument(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Disable Haystack instrumentation."""
        for wrapped_method in WRAPPED_METHODS:
            wrap_package = wrapped_method.get("package")
            wrap_object = wrapped_method.get("object")
            wrap_method = wrapped_method.get("method")

            if wrap_package and wrap_method:
                full_path = (
                    f"{wrap_package}.{wrap_object}" if wrap_object else wrap_package
                )
                self._safe_unwrap(full_path, wrap_method)

    def _safe_unwrap(self, module_path: str, method_name: str) -> None:
        """Safely unwrap a function, ignoring errors if not wrapped.

        Args:
            module_path: The full module path including class.
            method_name: The method name to unwrap.
        """
        try:
            unwrap(module_path, method_name)
        except (AttributeError, ValueError, ImportError, ModuleNotFoundError):
            pass
