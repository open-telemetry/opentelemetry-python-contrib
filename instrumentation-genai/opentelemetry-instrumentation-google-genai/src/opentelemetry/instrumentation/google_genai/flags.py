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

from os import environ
from typing import Union

from opentelemetry.instrumentation._semconv import _StabilityMode
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.util.genai.types import ContentCapturingMode
from opentelemetry.util.genai.utils import get_content_capturing_mode


def is_content_recording_enabled(
    mode: _StabilityMode,
) -> Union[bool, ContentCapturingMode]:
    if mode == _StabilityMode.DEFAULT:
        capture_content = environ.get(
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
        )
        return capture_content.lower() == "true"
    if mode == _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL:
        return get_content_capturing_mode()
    raise RuntimeError(f"{mode} mode not supported")
