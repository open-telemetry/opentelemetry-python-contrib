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


def get_content_capturing_mode() -> ContentCapturingMode:
    envvar = os.environ.get(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT)
    if (
        _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI,
        )
        == _StabilityMode.DEFAULT
    ):
        raise RuntimeError(
            "This function should never be called when StabilityMode is default.."
        )
    if not envvar:
        return ContentCapturingMode.NO_CONTENT
    try:
        return ContentCapturingMode[envvar.upper()]
    except KeyError:
        raise RuntimeError(
            f"{envvar} is not a valid option for `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` environment variable. Must be one of {', '.join(e.name for e in ContentCapturingMode)}"
        )
