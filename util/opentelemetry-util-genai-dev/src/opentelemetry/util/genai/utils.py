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

import logging
import os

from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES,
)
from opentelemetry.util.genai.types import ContentCapturingMode

logger = logging.getLogger(__name__)


def is_experimental_mode() -> bool:  # backward stub (always false)
    return False


def get_content_capturing_mode() -> (
    ContentCapturingMode
):  # single authoritative implementation
    value = os.environ.get(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES, "")
    if not value:
        return ContentCapturingMode.NO_CONTENT
    normalized = value.strip().lower()
    mapping = {
        "span": ContentCapturingMode.SPAN_ONLY,
        "events": ContentCapturingMode.EVENT_ONLY,
        "both": ContentCapturingMode.SPAN_AND_EVENT,
        "none": ContentCapturingMode.NO_CONTENT,
    }
    mode = mapping.get(normalized)
    if mode is not None:
        return mode
    logger.warning(
        "%s is not a valid option for `%s` environment variable. Must be one of span, events, both, none. Defaulting to `NO_CONTENT`.",
        value,
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES,
    )
    return ContentCapturingMode.NO_CONTENT
