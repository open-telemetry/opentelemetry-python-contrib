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
    if (
        _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI,
        )
        == _StabilityMode.DEFAULT
    ):
        raise ValueError(
            "This function should never be called when StabilityMode is default."
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
