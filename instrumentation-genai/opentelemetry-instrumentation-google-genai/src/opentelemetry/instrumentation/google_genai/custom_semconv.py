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


# Semantic Convention still being defined in:
# https://github.com/open-telemetry/semantic-conventions/pull/2125
GCP_GENAI_OPERATION_CONFIG = "gcp.gen_ai.operation.config"


# Semantic Convention to be defined.
# https://github.com/open-telemetry/semantic-conventions/issues/2183
TOOL_CALL_POSITIONAL_ARG_COUNT = "gen_ai.tool.positional_args.count"


# Semantic Convention to be defined.
# https://github.com/open-telemetry/semantic-conventions/issues/2183
TOOL_CALL_KEYWORD_ARG_COUNT = "gen_ai.tool.keyword_args.count"


# Semantic Convention to be defined.
# https://github.com/open-telemetry/semantic-conventions/issues/2185
FUNCTION_TOOL_CALL_START_EVENT_NAME = "function_call.start"
FUNCTION_TOOL_CALL_START_EVENT_ATTRS_POSITIONAL_ARGS_COUNT = (
    "positional_argument_count"
)
FUNCTION_TOOL_CALL_START_EVENT_ATTRS_KEYWORD_ARGS_COUNT = (
    "keyword_argument_count"
)
FUNCTION_TOOL_CALL_START_EVENT_BODY_POSITIONAL_ARGS = "positional_arguments"
FUNCTION_TOOL_CALL_START_EVENT_BODY_KEYWORD_ARGS = "keyword_arguments"


# Semantic Convention to be defined.
# https://github.com/open-telemetry/semantic-conventions/issues/2185
FUNCTION_TOOL_CALL_END_EVENT_NAME = "function_call.end"
FUNCTION_TOOL_CALL_END_EVENT_BODY_RESULT = "result"


# Semantic Convention to be defined.
# https://github.com/open-telemetry/semantic-conventions/issues/2184
CODE_MODULE = "code.module"
