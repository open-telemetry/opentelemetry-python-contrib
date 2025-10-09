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
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.util.genai.types import ContentCapturingMode

logger = logging.getLogger(__name__)


def get_content_capturing_mode() -> ContentCapturingMode:
    """This function should not be called when GEN_AI stability mode is set to DEFAULT.

    When the GEN_AI stability mode is DEFAULT this function will raise a ValueError -- see the code below."""
    envvar = os.environ.get(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT)
    try:
        signal = _OpenTelemetryStabilitySignalType.GEN_AI
    except AttributeError:
        signal = None

    if signal is not None:
        stability_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            signal
        )
        default_mode = stability_mode == _StabilityMode.DEFAULT
    else:
        stability_value = os.environ.get(
            OTEL_SEMCONV_STABILITY_OPT_IN, ""
        ).lower()
        default_mode = stability_value in {"", "default"}

    if default_mode:
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
