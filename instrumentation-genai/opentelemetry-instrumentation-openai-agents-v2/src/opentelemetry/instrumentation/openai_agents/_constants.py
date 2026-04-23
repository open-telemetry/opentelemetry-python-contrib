"""Shared constants for the OpenAI Agents instrumentation.

Centralises meter identity, metric instrument names, semantic convention
attribute keys, and operation name values so that ``span_processor`` and
``handler`` stay in sync without duplicating strings.
"""

from opentelemetry.semconv.attributes import (
    error_attributes as ErrorAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)


METER_NAME = "opentelemetry.instrumentation.openai_agents"
METER_VERSION = "0.1.0"

TOKEN_USAGE_METRIC = "gen_ai.client.token.usage"
OPERATION_DURATION_METRIC = "gen_ai.client.operation.duration"
TIME_TO_FIRST_TOKEN_METRIC = "gen_ai.server.time_to_first_token"



def _attr(name: str, fallback: str) -> str:
    return getattr(GenAIAttributes, name, fallback)


ERROR_TYPE = ErrorAttributes.ERROR_TYPE

GEN_AI_SYSTEM_KEY = getattr(GenAIAttributes, "GEN_AI_SYSTEM", "gen_ai.system")

GEN_AI_PROVIDER_NAME = _attr("GEN_AI_PROVIDER_NAME", "gen_ai.provider.name")
GEN_AI_OPERATION_NAME = _attr("GEN_AI_OPERATION_NAME", "gen_ai.operation.name")
GEN_AI_REQUEST_MODEL = _attr("GEN_AI_REQUEST_MODEL", "gen_ai.request.model")
GEN_AI_REQUEST_MAX_TOKENS = _attr(
    "GEN_AI_REQUEST_MAX_TOKENS", "gen_ai.request.max_tokens"
)
GEN_AI_REQUEST_TEMPERATURE = _attr(
    "GEN_AI_REQUEST_TEMPERATURE", "gen_ai.request.temperature"
)
GEN_AI_REQUEST_TOP_P = _attr("GEN_AI_REQUEST_TOP_P", "gen_ai.request.top_p")
GEN_AI_REQUEST_TOP_K = _attr("GEN_AI_REQUEST_TOP_K", "gen_ai.request.top_k")
GEN_AI_REQUEST_FREQUENCY_PENALTY = _attr(
    "GEN_AI_REQUEST_FREQUENCY_PENALTY", "gen_ai.request.frequency_penalty"
)
GEN_AI_REQUEST_PRESENCE_PENALTY = _attr(
    "GEN_AI_REQUEST_PRESENCE_PENALTY", "gen_ai.request.presence_penalty"
)
GEN_AI_REQUEST_CHOICE_COUNT = _attr(
    "GEN_AI_REQUEST_CHOICE_COUNT", "gen_ai.request.choice.count"
)
GEN_AI_REQUEST_STOP_SEQUENCES = _attr(
    "GEN_AI_REQUEST_STOP_SEQUENCES", "gen_ai.request.stop_sequences"
)
GEN_AI_REQUEST_ENCODING_FORMATS = _attr(
    "GEN_AI_REQUEST_ENCODING_FORMATS", "gen_ai.request.encoding_formats"
)
GEN_AI_REQUEST_SEED = _attr("GEN_AI_REQUEST_SEED", "gen_ai.request.seed")
GEN_AI_RESPONSE_ID = _attr("GEN_AI_RESPONSE_ID", "gen_ai.response.id")
GEN_AI_RESPONSE_MODEL = _attr(
    "GEN_AI_RESPONSE_MODEL", "gen_ai.response.model"
)
GEN_AI_RESPONSE_FINISH_REASONS = _attr(
    "GEN_AI_RESPONSE_FINISH_REASONS", "gen_ai.response.finish_reasons"
)
GEN_AI_USAGE_INPUT_TOKENS = _attr(
    "GEN_AI_USAGE_INPUT_TOKENS", "gen_ai.usage.input_tokens"
)
GEN_AI_USAGE_OUTPUT_TOKENS = _attr(
    "GEN_AI_USAGE_OUTPUT_TOKENS", "gen_ai.usage.output_tokens"
)
GEN_AI_CONVERSATION_ID = _attr(
    "GEN_AI_CONVERSATION_ID", "gen_ai.conversation.id"
)
GEN_AI_AGENT_ID = _attr("GEN_AI_AGENT_ID", "gen_ai.agent.id")
GEN_AI_AGENT_NAME = _attr("GEN_AI_AGENT_NAME", "gen_ai.agent.name")
GEN_AI_AGENT_DESCRIPTION = _attr(
    "GEN_AI_AGENT_DESCRIPTION", "gen_ai.agent.description"
)
GEN_AI_TOOL_NAME = _attr("GEN_AI_TOOL_NAME", "gen_ai.tool.name")
GEN_AI_TOOL_TYPE = _attr("GEN_AI_TOOL_TYPE", "gen_ai.tool.type")
GEN_AI_TOOL_CALL_ID = _attr("GEN_AI_TOOL_CALL_ID", "gen_ai.tool.call.id")
GEN_AI_TOOL_DESCRIPTION = _attr(
    "GEN_AI_TOOL_DESCRIPTION", "gen_ai.tool.description"
)
GEN_AI_OUTPUT_TYPE = _attr("GEN_AI_OUTPUT_TYPE", "gen_ai.output.type")
GEN_AI_SYSTEM_INSTRUCTIONS = _attr(
    "GEN_AI_SYSTEM_INSTRUCTIONS", "gen_ai.system_instructions"
)
GEN_AI_INPUT_MESSAGES = _attr("GEN_AI_INPUT_MESSAGES", "gen_ai.input.messages")
GEN_AI_OUTPUT_MESSAGES = _attr(
    "GEN_AI_OUTPUT_MESSAGES", "gen_ai.output.messages"
)
GEN_AI_DATA_SOURCE_ID = _attr(
    "GEN_AI_DATA_SOURCE_ID", "gen_ai.data_source.id"
)
GEN_AI_TOKEN_TYPE = _attr("GEN_AI_TOKEN_TYPE", "gen_ai.token.type")

# The semantic conventions currently expose multiple usage token attributes;
# we retain the completion/prompt aliases for backwards compatibility.
GEN_AI_USAGE_PROMPT_TOKENS = _attr(
    "GEN_AI_USAGE_PROMPT_TOKENS", "gen_ai.usage.prompt_tokens"
)
GEN_AI_USAGE_COMPLETION_TOKENS = _attr(
    "GEN_AI_USAGE_COMPLETION_TOKENS", "gen_ai.usage.completion_tokens"
)

# Attributes not (yet) defined in the spec retain their literal values.
GEN_AI_TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
GEN_AI_TOOL_CALL_RESULT = "gen_ai.tool.call.result"
GEN_AI_TOOL_DEFINITIONS = "gen_ai.tool.definitions"
GEN_AI_ORCHESTRATOR_AGENT_DEFINITIONS = "gen_ai.orchestrator.agent.definitions"
GEN_AI_GUARDRAIL_NAME = "gen_ai.guardrail.name"
GEN_AI_GUARDRAIL_TRIGGERED = "gen_ai.guardrail.triggered"
GEN_AI_HANDOFF_FROM_AGENT = "gen_ai.handoff.from_agent"
GEN_AI_HANDOFF_TO_AGENT = "gen_ai.handoff.to_agent"
GEN_AI_EMBEDDINGS_DIMENSION_COUNT = "gen_ai.embeddings.dimension.count"

GEN_AI_SESSION_ID = "gen_ai.session.id"
GEN_AI_RESPONSE_STATUS = "gen_ai.response.status"


SERVER_ADDRESS = ServerAttributes.SERVER_ADDRESS
SERVER_PORT = ServerAttributes.SERVER_PORT


INVOKE_AGENT = GenAIAttributes.GenAiOperationNameValues.INVOKE_AGENT.value
EXECUTE_TOOL = GenAIAttributes.GenAiOperationNameValues.EXECUTE_TOOL.value
GENERATE_CONTENT = (
    GenAIAttributes.GenAiOperationNameValues.GENERATE_CONTENT.value
)
