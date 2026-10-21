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
from unittest.mock import patch

from google.genai import types

from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)

from .base import TestCase

_JSON_SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string", "enum": ["Paris", "London"]}},
    "required": ["city"],
    "additionalProperties": False,
}
_PARAMETERS = {
    "type": "OBJECT",
    "properties": {"city": {"type": "STRING"}},
    "required": ["city"],
}


def _expected(parameters):
    return [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get the weather for a city.",
            "parameters": parameters,
        }
    ]


class ToolDefinitionParametersTestCase(TestCase):
    def _get_tool_definitions(self, **parameter_fields):
        # Patched per call: the base setUp replaces the stability mapping dict.
        with (
            patch.dict(
                "os.environ",
                {
                    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "SPAN_ONLY",
                    "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
                },
            ),
            patch.dict(
                _OpenTelemetrySemanticConventionStability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING,
                {
                    _OpenTelemetryStabilitySignalType.GEN_AI: _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
                },
            ),
        ):
            self.configure_valid_response(text="Sunny.")
            declaration = types.FunctionDeclaration(
                name="get_weather",
                description="Get the weather for a city.",
                **parameter_fields,
            )
            self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents="What is the weather in Paris?",
                config=types.GenerateContentConfig(
                    tools=[types.Tool(function_declarations=[declaration])]
                ),
            )
            span = self.otel.get_span_named(
                "generate_content gemini-2.5-flash"
            )
            return json.loads(span.attributes["gen_ai.tool.definitions"])

    def test_json_schema(self):
        self.assertEqual(
            self._get_tool_definitions(parameters_json_schema=_JSON_SCHEMA),
            _expected(_JSON_SCHEMA),
        )

    def test_empty_json_schema(self):
        self.assertEqual(
            self._get_tool_definitions(parameters_json_schema={}),
            _expected({}),
        )

    def test_parameters_wins(self):
        self.assertEqual(
            self._get_tool_definitions(
                parameters=_PARAMETERS, parameters_json_schema=_JSON_SCHEMA
            ),
            _expected(_PARAMETERS),
        )
