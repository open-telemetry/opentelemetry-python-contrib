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

import json
import logging
import os
from base64 import b64encode
from functools import partial
from typing import Any

from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT,
)
from opentelemetry.util.genai.types import ContentCapturingMode

logger = logging.getLogger(__name__)


def is_experimental_mode() -> bool:
    return (
        _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI,
        )
        is _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
    )


def get_content_capturing_mode() -> ContentCapturingMode:
    """This function should not be called when GEN_AI stability mode is set to DEFAULT.

    When the GEN_AI stability mode is DEFAULT this function will raise a ValueError -- see the code below."""
    envvar = os.environ.get(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT)
    if not is_experimental_mode():
        raise ValueError(
            "This function should never be called when StabilityMode is not experimental."
        )
    if not envvar:
        return ContentCapturingMode.NO_CONTENT
    try:
        return ContentCapturingMode[envvar.upper()]
    except KeyError:
        logger.warning(
            "%s is not a valid option for `%s` environment variable. Must be one of %s. Defaulting to `NO_CONTENT`.",
            envvar,
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
            ", ".join(e.name for e in ContentCapturingMode),
        )
        return ContentCapturingMode.NO_CONTENT


def should_emit_event() -> bool:
    """Check if event emission is enabled.

    Returns True if event emission is enabled, False otherwise.

    If the environment variable OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT is explicitly set,
    its value takes precedence. Otherwise, the default value is determined by
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT:
    - NO_CONTENT or SPAN_ONLY: defaults to False
    - EVENT_ONLY or SPAN_AND_EVENT: defaults to True
    """
    envvar = os.environ.get(OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT)
    # If explicitly set (and not empty), use the user's value (highest priority)
    if envvar and envvar.strip():
        envvar_lower = envvar.lower().strip()
        if envvar_lower == "true":
            return True
        if envvar_lower == "false":
            return False
        logger.warning(
            "%s is not a valid option for `%s` environment variable. Must be one of true or false (case-insensitive). Defaulting based on content capturing mode.",
            envvar,
            OTEL_INSTRUMENTATION_GENAI_EMIT_EVENT,
        )
        # Invalid value falls through to default logic below

    # If not explicitly set (or invalid), determine default based on content capturing mode
    try:
        if not is_experimental_mode():
            # Not in experimental mode, default to False
            return False
        content_mode = get_content_capturing_mode()
        # EVENT_ONLY and SPAN_AND_EVENT require events, so default to True
        if content_mode in (
            ContentCapturingMode.EVENT_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        ):
            return True
        # NO_CONTENT and SPAN_ONLY don't require events, so default to False
        return False
    except ValueError:
        # If get_content_capturing_mode raises ValueError (not in experimental mode),
        # default to False
        return False


class _GenAiJsonEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, bytes):
            return b64encode(o).decode()
        return super().default(o)


gen_ai_json_dump = partial(
    json.dump, separators=(",", ":"), cls=_GenAiJsonEncoder
)
"""Should be used by GenAI instrumentations when serializing objects that may contain
bytes, datetimes, etc. for GenAI observability."""

gen_ai_json_dumps = partial(
    json.dumps, separators=(",", ":"), cls=_GenAiJsonEncoder
)
"""Should be used by GenAI instrumentations when serializing objects that may contain
bytes, datetimes, etc. for GenAI observability."""
