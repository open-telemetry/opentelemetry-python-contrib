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

from __future__ import annotations

from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    Error,
)

from .utils import (
    create_chat_invocation,
    set_response_attributes,
)


def chat_create(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap ``V2Client.chat`` to emit GenAI telemetry."""
    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    def traced_method(wrapped, instance, args, kwargs):
        invocation = handler.start_llm(
            create_chat_invocation(kwargs, instance, capture_content=capture_content)
        )
        try:
            result = wrapped(*args, **kwargs)
            set_response_attributes(invocation, result, capture_content)
            handler.stop_llm(invocation)
            return result
        except Exception as error:
            handler.fail_llm(
                invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method


def async_chat_create(
    handler: TelemetryHandler,
    content_capturing_mode: ContentCapturingMode,
):
    """Wrap ``AsyncV2Client.chat`` to emit GenAI telemetry."""
    capture_content = content_capturing_mode != ContentCapturingMode.NO_CONTENT

    async def traced_method(wrapped, instance, args, kwargs):
        invocation = handler.start_llm(
            create_chat_invocation(kwargs, instance, capture_content=capture_content)
        )
        try:
            result = await wrapped(*args, **kwargs)
            set_response_attributes(invocation, result, capture_content)
            handler.stop_llm(invocation)
            return result
        except Exception as error:
            handler.fail_llm(
                invocation, Error(type=type(error), message=str(error))
            )
            raise

    return traced_method
