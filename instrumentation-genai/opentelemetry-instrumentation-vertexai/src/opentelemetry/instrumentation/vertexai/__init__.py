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

from typing import Any, Collection

from wrapt import (
    wrap_function_wrapper,  # type: ignore[reportUnknownVariableType]
)

from opentelemetry._events import get_event_logger
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.instrumentation.vertexai.package import _instruments
from opentelemetry.instrumentation.vertexai.patch import (
    generate_content_create,
)
from opentelemetry.instrumentation.vertexai.utils import is_content_enabled
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer


def _client_classes():
    # This import is very slow, do it lazily in case instrument() is not called

    # pylint: disable=import-outside-toplevel
    from google.cloud.aiplatform_v1.services.prediction_service import (
        client,
    )
    from google.cloud.aiplatform_v1beta1.services.prediction_service import (
        client as client_v1beta1,
    )

    return (
        client.PredictionServiceClient,
        client_v1beta1.PredictionServiceClient,
    )


class VertexAIInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any):
        """Enable VertexAI instrumentation."""
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )
        event_logger_provider = kwargs.get("event_logger_provider")
        event_logger = get_event_logger(
            __name__,
            "",
            schema_url=Schemas.V1_28_0.value,
            event_logger_provider=event_logger_provider,
        )

        for client_class in _client_classes():
            wrap_function_wrapper(
                client_class,
                name="generate_content",
                wrapper=generate_content_create(
                    tracer, event_logger, is_content_enabled()
                ),
            )

    def _uninstrument(self, **kwargs: Any) -> None:
        for client_class in _client_classes():
            unwrap(client_class, "generate_content")
