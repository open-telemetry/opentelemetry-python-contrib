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

from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE,
)
from opentelemetry.util.genai.types import ContentCapturingMode

logger = logging.getLogger(__name__)


def is_experimental_mode() -> bool:
    # Workaround: Check environment variable directly since the stability class
    # initialization seems unreliable (can be initialized before env vars are set)
    opt_in = os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN", "")
    if "gen_ai_latest_experimental" in opt_in.lower():
        return True

    # Fallback to the official check
    # TODO stability mode is being set to default even after setting OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental
    signal_type = getattr(
        _OpenTelemetryStabilitySignalType, "GEN_AI", None
    )
    if signal_type is None:
        logger.debug(
            "GEN_AI stability signal missing in OpenTelemetry; assuming non-experimental mode"
        )
        return False
    experimental_mode = getattr(
        _StabilityMode, "GEN_AI_LATEST_EXPERIMENTAL", None
    )
    if experimental_mode is None:
        logger.debug(
            "GEN_AI_LATEST_EXPERIMENTAL stability mode missing; assuming non-experimental mode"
        )
        return False
    return (
        _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(  # noqa: SLF001
            signal_type,
        )
        == experimental_mode
    )


def get_content_capturing_mode() -> (
    ContentCapturingMode
):  # single authoritative implementation
    capture_message_content = os.environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
    )
    capture_message_content_mode = os.environ.get(
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE
    )
    if not capture_message_content:
        return ContentCapturingMode.NO_CONTENT
    if not is_experimental_mode():
        return ContentCapturingMode.NO_CONTENT

    primary = (capture_message_content or "").strip()
    secondary = (capture_message_content_mode or "").strip()

    def _convert(tok: str) -> ContentCapturingMode | None:
        if not tok:
            return None
        u = tok.upper()
        if u in ContentCapturingMode.__members__:
            return ContentCapturingMode[u]
        if u in ("TRUE", "1", "YES"):
            return ContentCapturingMode.SPAN_ONLY
        return None

    # If secondary mode is specified, it takes precedence
    if secondary:
        sec_mode = _convert(secondary)
        if sec_mode is not None:
            return sec_mode

    # Otherwise use primary mode
    prim_mode = _convert(primary)
    if prim_mode is not None:
        return prim_mode

    logger.warning(
        "%s is not a valid option for `%s` environment variable. Must be one of %s. Defaulting to `NO_CONTENT`.",
        primary,
        OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
        ", ".join(e.name for e in ContentCapturingMode),
    )
    return ContentCapturingMode.NO_CONTENT
