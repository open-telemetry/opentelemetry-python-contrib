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

"""Per-operation attribute matrix based on OTel GenAI semantic conventions.

Single source of truth for which attributes apply to which operations
in the LangChain instrumentor. Attribute requirement levels follow:
https://opentelemetry.io/docs/specs/semconv/gen-ai/
"""

from __future__ import annotations

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAI,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as Server,
)
from opentelemetry.semconv.attributes import (
    error_attributes as Error,
)
from opentelemetry.trace import SpanKind

# ---------------------------------------------------------------------------
# Operation name constants
# ---------------------------------------------------------------------------

OP_CHAT = GenAI.GenAiOperationNameValues.CHAT.value  # "chat"
OP_TEXT_COMPLETION = (
    GenAI.GenAiOperationNameValues.TEXT_COMPLETION.value
)  # "text_completion"
OP_INVOKE_AGENT = (
    GenAI.GenAiOperationNameValues.INVOKE_AGENT.value
)  # "invoke_agent"
OP_EXECUTE_TOOL = (
    GenAI.GenAiOperationNameValues.EXECUTE_TOOL.value
)  # "execute_tool"

# These operations are not yet in the semconv enum; define as literals.
OP_INVOKE_WORKFLOW = "invoke_workflow"
OP_RETRIEVAL = "retrieval"

# ---------------------------------------------------------------------------
# Attribute key aliases (not yet in the released semconv package)
# ---------------------------------------------------------------------------

GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS = (
    "gen_ai.usage.cache_creation.input_tokens"
)
GEN_AI_AGENT_VERSION = "gen_ai.agent.version"
GEN_AI_WORKFLOW_NAME = "gen_ai.workflow.name"

# ---------------------------------------------------------------------------
# Attribute sets per operation, grouped by requirement level
#
# Requirement levels (per OpenTelemetry specification):
#   REQUIRED           – MUST be provided.
#   CONDITIONALLY_REQ  – MUST be provided when the stated condition is met.
#   RECOMMENDED        – SHOULD be provided.
#   OPT_IN             – MAY be provided; typically gated by a config flag.
# ---------------------------------------------------------------------------

# ---- chat / text_completion (inference client spans) ----------------------

INFERENCE_REQUIRED: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_OPERATION_NAME,
        GenAI.GEN_AI_PROVIDER_NAME,
    }
)

INFERENCE_CONDITIONALLY_REQUIRED: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_REQUEST_MODEL,  # if available
        Error.ERROR_TYPE,  # if response is an error
        Server.SERVER_PORT,  # if server.address is set
        GenAI.GEN_AI_REQUEST_SEED,  # if present in request
        GenAI.GEN_AI_REQUEST_CHOICE_COUNT,  # if != 1
        GenAI.GEN_AI_OUTPUT_TYPE,  # if applicable
        GenAI.GEN_AI_CONVERSATION_ID,  # if available
    }
)

INFERENCE_RECOMMENDED: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_REQUEST_MAX_TOKENS,
        GenAI.GEN_AI_REQUEST_TEMPERATURE,
        GenAI.GEN_AI_REQUEST_TOP_P,
        GenAI.GEN_AI_REQUEST_TOP_K,
        GenAI.GEN_AI_REQUEST_STOP_SEQUENCES,
        GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY,
        GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY,
        GenAI.GEN_AI_RESPONSE_ID,
        GenAI.GEN_AI_RESPONSE_MODEL,
        GenAI.GEN_AI_RESPONSE_FINISH_REASONS,
        GenAI.GEN_AI_USAGE_INPUT_TOKENS,
        GenAI.GEN_AI_USAGE_OUTPUT_TOKENS,
        GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
        GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
        Server.SERVER_ADDRESS,
    }
)

INFERENCE_OPT_IN: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_SYSTEM_INSTRUCTIONS,
        GenAI.GEN_AI_INPUT_MESSAGES,
        GenAI.GEN_AI_OUTPUT_MESSAGES,
        GenAI.GEN_AI_TOOL_DEFINITIONS,
    }
)

# ---- invoke_agent --------------------------------------------------------

AGENT_REQUIRED: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_OPERATION_NAME,
        GenAI.GEN_AI_PROVIDER_NAME,
    }
)

AGENT_CONDITIONALLY_REQUIRED: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_AGENT_ID,
        GenAI.GEN_AI_AGENT_NAME,
        GenAI.GEN_AI_AGENT_DESCRIPTION,
        GEN_AI_AGENT_VERSION,
        GenAI.GEN_AI_REQUEST_MODEL,
        GenAI.GEN_AI_DATA_SOURCE_ID,
        Error.ERROR_TYPE,  # if response is an error
        GenAI.GEN_AI_CONVERSATION_ID,
    }
)

AGENT_RECOMMENDED: frozenset[str] = frozenset(
    {
        Server.SERVER_ADDRESS,
        # All inference request/response attributes are also recommended
        GenAI.GEN_AI_REQUEST_MAX_TOKENS,
        GenAI.GEN_AI_REQUEST_TEMPERATURE,
        GenAI.GEN_AI_REQUEST_TOP_P,
        GenAI.GEN_AI_REQUEST_TOP_K,
        GenAI.GEN_AI_REQUEST_STOP_SEQUENCES,
        GenAI.GEN_AI_REQUEST_FREQUENCY_PENALTY,
        GenAI.GEN_AI_REQUEST_PRESENCE_PENALTY,
        GenAI.GEN_AI_RESPONSE_ID,
        GenAI.GEN_AI_RESPONSE_MODEL,
        GenAI.GEN_AI_RESPONSE_FINISH_REASONS,
        GenAI.GEN_AI_USAGE_INPUT_TOKENS,
        GenAI.GEN_AI_USAGE_OUTPUT_TOKENS,
        GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
        GEN_AI_USAGE_CACHE_CREATION_INPUT_TOKENS,
    }
)

AGENT_OPT_IN: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_SYSTEM_INSTRUCTIONS,
        GenAI.GEN_AI_INPUT_MESSAGES,
        GenAI.GEN_AI_OUTPUT_MESSAGES,
    }
)

# ---- execute_tool --------------------------------------------------------

TOOL_REQUIRED: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_OPERATION_NAME,
    }
)

TOOL_CONDITIONALLY_REQUIRED: frozenset[str] = frozenset(
    {
        Error.ERROR_TYPE,  # if response is an error
    }
)

TOOL_RECOMMENDED: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_TOOL_NAME,
        GenAI.GEN_AI_TOOL_CALL_ID,
        GenAI.GEN_AI_TOOL_DESCRIPTION,
        GenAI.GEN_AI_TOOL_TYPE,
    }
)

TOOL_OPT_IN: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_TOOL_CALL_ARGUMENTS,
        GenAI.GEN_AI_TOOL_CALL_RESULT,
    }
)

# ---- invoke_workflow -----------------------------------------------------

WORKFLOW_REQUIRED: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_OPERATION_NAME,
    }
)

WORKFLOW_CONDITIONALLY_REQUIRED: frozenset[str] = frozenset(
    {
        Error.ERROR_TYPE,  # if response is an error
        GEN_AI_WORKFLOW_NAME,  # if available
    }
)

WORKFLOW_RECOMMENDED: frozenset[str] = frozenset()

WORKFLOW_OPT_IN: frozenset[str] = frozenset(
    {
        GenAI.GEN_AI_INPUT_MESSAGES,
        GenAI.GEN_AI_OUTPUT_MESSAGES,
    }
)

# ---------------------------------------------------------------------------
# Aggregate lookup: operation → (required, conditionally_required,
#                                 recommended, opt_in)
# ---------------------------------------------------------------------------

OPERATION_ATTRIBUTES: dict[
    str,
    tuple[
        frozenset[str],
        frozenset[str],
        frozenset[str],
        frozenset[str],
    ],
] = {
    OP_CHAT: (
        INFERENCE_REQUIRED,
        INFERENCE_CONDITIONALLY_REQUIRED,
        INFERENCE_RECOMMENDED,
        INFERENCE_OPT_IN,
    ),
    OP_TEXT_COMPLETION: (
        INFERENCE_REQUIRED,
        INFERENCE_CONDITIONALLY_REQUIRED,
        INFERENCE_RECOMMENDED,
        INFERENCE_OPT_IN,
    ),
    OP_INVOKE_AGENT: (
        AGENT_REQUIRED,
        AGENT_CONDITIONALLY_REQUIRED,
        AGENT_RECOMMENDED,
        AGENT_OPT_IN,
    ),
    OP_EXECUTE_TOOL: (
        TOOL_REQUIRED,
        TOOL_CONDITIONALLY_REQUIRED,
        TOOL_RECOMMENDED,
        TOOL_OPT_IN,
    ),
    OP_INVOKE_WORKFLOW: (
        WORKFLOW_REQUIRED,
        WORKFLOW_CONDITIONALLY_REQUIRED,
        WORKFLOW_RECOMMENDED,
        WORKFLOW_OPT_IN,
    ),
}

# ---------------------------------------------------------------------------
# SpanKind helper
# ---------------------------------------------------------------------------

_CLIENT_OPERATIONS: frozenset[str] = frozenset(
    {OP_CHAT, OP_TEXT_COMPLETION, OP_INVOKE_AGENT}
)


def get_operation_span_kind(operation: str) -> SpanKind:
    """Return the correct SpanKind for the given operation.

    * ``chat``, ``text_completion``, ``invoke_agent`` → ``SpanKind.CLIENT``
    * ``execute_tool``, ``invoke_workflow``, and others → ``SpanKind.INTERNAL``
    """
    if operation in _CLIENT_OPERATIONS:
        return SpanKind.CLIENT
    return SpanKind.INTERNAL


# ---------------------------------------------------------------------------
# Metric applicability
#
# Maps metric instrument names to the set of operations they apply to.
# ---------------------------------------------------------------------------

METRIC_OPERATION_DURATION = "gen_ai.client.operation.duration"
METRIC_TOKEN_USAGE = "gen_ai.client.token.usage"
METRIC_TIME_TO_FIRST_CHUNK = "gen_ai.client.operation.time_to_first_chunk"
METRIC_TIME_PER_OUTPUT_CHUNK = "gen_ai.client.operation.time_per_output_chunk"

METRIC_APPLICABLE_OPERATIONS: dict[str, frozenset[str]] = {
    METRIC_OPERATION_DURATION: frozenset({OP_CHAT, OP_TEXT_COMPLETION}),
    METRIC_TOKEN_USAGE: frozenset({OP_CHAT, OP_TEXT_COMPLETION}),
    # Streaming-only metrics (chat / text_completion)
    METRIC_TIME_TO_FIRST_CHUNK: frozenset({OP_CHAT, OP_TEXT_COMPLETION}),
    METRIC_TIME_PER_OUTPUT_CHUNK: frozenset({OP_CHAT, OP_TEXT_COMPLETION}),
}
