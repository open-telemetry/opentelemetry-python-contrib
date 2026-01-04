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
VertexAI client instrumentation supporting `google-cloud-aiplatform` SDK, it can be enabled by
using ``VertexAIInstrumentor``.

.. _vertexai: https://pypi.org/project/google-cloud-aiplatform/

Usage
-----

.. code:: python

    import vertexai
    from vertexai.generative_models import GenerativeModel
    from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor

    VertexAIInstrumentor().instrument()

    vertexai.init()
    model = GenerativeModel("gemini-1.5-flash-002")
    chat_completion = model.generate_content(
        "Write a short poem on OpenTelemetry."
    )

API
---
"""

from __future__ import annotations

from typing import Any, Collection

from wrapt import (
    wrap_function_wrapper,  # type: ignore[reportUnknownVariableType]
)

from opentelemetry._logs import get_logger
from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.instrumentation.vertexai.high_level_patch import (
    LEGACY_CHAT_SESSION_METHODS,
    TEXT_GENERATION_METHODS,
    HighLevelMethodWrappers,
)
from opentelemetry.instrumentation.vertexai.package import _instruments
from opentelemetry.instrumentation.vertexai.patch import MethodWrappers
from opentelemetry.instrumentation.vertexai.utils import is_content_enabled
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer
from opentelemetry.util.genai.completion_hook import load_completion_hook


def _methods_to_wrap(
    method_wrappers: MethodWrappers,
):
    # This import is very slow, do it lazily in case instrument() is not called
    # pylint: disable=import-outside-toplevel
    from google.cloud.aiplatform_v1.services.prediction_service import (  # noqa: PLC0415
        async_client,
        client,
    )
    from google.cloud.aiplatform_v1beta1.services.prediction_service import (  # noqa: PLC0415
        async_client as async_client_v1beta1,
    )
    from google.cloud.aiplatform_v1beta1.services.prediction_service import (  # noqa: PLC0415
        client as client_v1beta1,
    )

    for client_class in (
        client.PredictionServiceClient,
        client_v1beta1.PredictionServiceClient,
    ):
        yield (
            client_class,
            client_class.generate_content.__name__,  # type: ignore[reportUnknownMemberType]
            method_wrappers.generate_content,
        )

    for client_class in (
        async_client.PredictionServiceAsyncClient,
        async_client_v1beta1.PredictionServiceAsyncClient,
    ):
        yield (
            client_class,
            client_class.generate_content.__name__,  # type: ignore[reportUnknownMemberType]
            method_wrappers.agenerate_content,
        )


def _high_level_methods_to_wrap(
    high_level_wrappers: HighLevelMethodWrappers,
):
    """Yield high-level API methods to wrap (TextGenerationModel, legacy ChatSession)."""
    # pylint: disable=import-outside-toplevel
    import importlib  # noqa: PLC0415
    import logging  # noqa: PLC0415

    logger = logging.getLogger(__name__)

    # Map method names to wrapper functions
    wrapper_map = {
        ("TextGenerationModel", "predict", False, False): high_level_wrappers.predict,
        ("TextGenerationModel", "predict_async", True, False): high_level_wrappers.apredict,
        ("TextGenerationModel", "predict_streaming", False, True): high_level_wrappers.predict_streaming,
        ("TextGenerationModel", "predict_streaming_async", True, True): high_level_wrappers.apredict_streaming,
        ("ChatSession", "send_message", False, False): high_level_wrappers.send_message,
        ("ChatSession", "send_message_streaming", False, True): high_level_wrappers.send_message_streaming,
    }

    all_methods = TEXT_GENERATION_METHODS + LEGACY_CHAT_SESSION_METHODS

    for method_info in all_methods:
        package = method_info["package"]
        obj_name = method_info["object"]
        method_name = method_info["method"]
        is_async = method_info["is_async"]
        is_streaming = method_info.get("is_streaming", False)

        try:
            module = importlib.import_module(package)
            obj_class = getattr(module, obj_name, None)
            if obj_class is None:
                logger.debug(
                    "Could not find %s.%s for instrumentation",
                    package,
                    obj_name,
                )
                continue

            wrapper_key = (obj_name, method_name, is_async, is_streaming)
            wrapper = wrapper_map.get(wrapper_key)
            if wrapper is None:
                logger.debug(
                    "No wrapper found for %s.%s",
                    obj_name,
                    method_name,
                )
                continue

            yield (obj_class, method_name, wrapper)

        except ImportError:
            # Module not available, skip silently
            logger.debug(
                "Could not import %s for instrumentation",
                package,
            )
            continue


class VertexAIInstrumentor(BaseInstrumentor):
    def __init__(self) -> None:
        super().__init__()
        self._methods_to_unwrap: list[tuple[Any, str]] = []

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        """Enable VertexAI instrumentation."""
        completion_hook = (
            kwargs.get("completion_hook") or load_completion_hook()
        )
        sem_conv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI,
        )
        tracer_provider = kwargs.get("tracer_provider")
        schema = (
            Schemas.V1_28_0.value
            if sem_conv_opt_in_mode == _StabilityMode.DEFAULT
            else Schemas.V1_36_0.value
        )
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=schema,
        )
        logger_provider = kwargs.get("logger_provider")
        logger = get_logger(
            __name__,
            "",
            logger_provider=logger_provider,
            schema_url=schema,
        )
        sem_conv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI,
        )
        if sem_conv_opt_in_mode == _StabilityMode.DEFAULT:
            # Type checker now knows sem_conv_opt_in_mode is a Literal[_StabilityMode.DEFAULT]
            method_wrappers = MethodWrappers(
                tracer,
                logger,
                is_content_enabled(sem_conv_opt_in_mode),
                sem_conv_opt_in_mode,
                completion_hook,
            )
            high_level_wrappers = HighLevelMethodWrappers(
                tracer,
                logger,
                is_content_enabled(sem_conv_opt_in_mode),
                sem_conv_opt_in_mode,
            )
        elif sem_conv_opt_in_mode == _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL:
            # Type checker now knows it's the other literal
            method_wrappers = MethodWrappers(
                tracer,
                logger,
                is_content_enabled(sem_conv_opt_in_mode),
                sem_conv_opt_in_mode,
                completion_hook,
            )
            high_level_wrappers = HighLevelMethodWrappers(
                tracer,
                logger,
                is_content_enabled(sem_conv_opt_in_mode),
                sem_conv_opt_in_mode,
            )
        else:
            raise RuntimeError(f"{sem_conv_opt_in_mode} mode not supported")

        # Wrap low-level PredictionServiceClient methods
        for client_class, method_name, wrapper in _methods_to_wrap(
            method_wrappers
        ):
            wrap_function_wrapper(
                client_class,
                name=method_name,
                wrapper=wrapper,
            )
            self._methods_to_unwrap.append((client_class, method_name))

        # Wrap high-level TextGenerationModel and legacy ChatSession methods
        for obj_class, method_name, wrapper in _high_level_methods_to_wrap(
            high_level_wrappers
        ):
            wrap_function_wrapper(
                obj_class,
                name=method_name,
                wrapper=wrapper,
            )
            self._methods_to_unwrap.append((obj_class, method_name))

    def _uninstrument(self, **kwargs: Any) -> None:
        for client_class, method_name in self._methods_to_unwrap:
            unwrap(client_class, method_name)
