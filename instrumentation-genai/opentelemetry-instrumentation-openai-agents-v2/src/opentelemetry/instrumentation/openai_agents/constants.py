"""Centralized semantic convention constants for GenAI instrumentation.

Consolidates provider names, operation names, tool types, output types,
evaluation attributes, and helper maps so other modules can import from
one place. Keeping strings in one module reduces drift as the spec evolves.
"""

from __future__ import annotations

from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)


def _enum_values(enum_cls) -> dict[str, str]:
    """Return mapping of enum member name to value."""
    return {member.name: member.value for member in enum_cls}


_PROVIDER_VALUES = _enum_values(GenAIAttributes.GenAiProviderNameValues)


class GenAIProvider:
    OPENAI = _PROVIDER_VALUES["OPENAI"]
    GCP_GEN_AI = _PROVIDER_VALUES["GCP_GEN_AI"]
    GCP_VERTEX_AI = _PROVIDER_VALUES["GCP_VERTEX_AI"]
    GCP_GEMINI = _PROVIDER_VALUES["GCP_GEMINI"]
    ANTHROPIC = _PROVIDER_VALUES["ANTHROPIC"]
    COHERE = _PROVIDER_VALUES["COHERE"]
    AZURE_AI_INFERENCE = _PROVIDER_VALUES["AZURE_AI_INFERENCE"]
    AZURE_AI_OPENAI = _PROVIDER_VALUES["AZURE_AI_OPENAI"]
    IBM_WATSONX_AI = _PROVIDER_VALUES["IBM_WATSONX_AI"]
    AWS_BEDROCK = _PROVIDER_VALUES["AWS_BEDROCK"]
    PERPLEXITY = _PROVIDER_VALUES["PERPLEXITY"]
    X_AI = _PROVIDER_VALUES["X_AI"]
    DEEPSEEK = _PROVIDER_VALUES["DEEPSEEK"]
    GROQ = _PROVIDER_VALUES["GROQ"]
    MISTRAL_AI = _PROVIDER_VALUES["MISTRAL_AI"]

    ALL = set(_PROVIDER_VALUES.values())


_OPERATION_VALUES = _enum_values(GenAIAttributes.GenAiOperationNameValues)


class GenAIOperationName:
    CHAT = _OPERATION_VALUES["CHAT"]
    GENERATE_CONTENT = _OPERATION_VALUES["GENERATE_CONTENT"]
    TEXT_COMPLETION = _OPERATION_VALUES["TEXT_COMPLETION"]
    EMBEDDINGS = _OPERATION_VALUES["EMBEDDINGS"]
    CREATE_AGENT = _OPERATION_VALUES["CREATE_AGENT"]
    INVOKE_AGENT = _OPERATION_VALUES["INVOKE_AGENT"]
    EXECUTE_TOOL = _OPERATION_VALUES["EXECUTE_TOOL"]
    # Operations below are not yet covered by the spec but remain for backwards compatibility
    TRANSCRIPTION = "transcription"
    SPEECH = "speech_generation"
    GUARDRAIL = "guardrail_check"
    HANDOFF = "agent_handoff"
    RESPONSE = "response"  # internal aggregator in current processor

    CLASS_FALLBACK = {
        "generationspan": CHAT,
        "responsespan": RESPONSE,
        "functionspan": EXECUTE_TOOL,
        "agentspan": INVOKE_AGENT,
    }


_OUTPUT_VALUES = _enum_values(GenAIAttributes.GenAiOutputTypeValues)


class GenAIOutputType:
    TEXT = _OUTPUT_VALUES["TEXT"]
    JSON = _OUTPUT_VALUES["JSON"]
    IMAGE = _OUTPUT_VALUES["IMAGE"]
    SPEECH = _OUTPUT_VALUES["SPEECH"]


class GenAIToolType:
    FUNCTION = "function"
    EXTENSION = "extension"
    DATASTORE = "datastore"

    ALL = {FUNCTION, EXTENSION, DATASTORE}


class GenAIEvaluationAttributes:
    NAME = "gen_ai.evaluation.name"
    SCORE_VALUE = "gen_ai.evaluation.score.value"
    SCORE_LABEL = "gen_ai.evaluation.score.label"
    EXPLANATION = "gen_ai.evaluation.explanation"


def _attr(name: str, fallback: str) -> str:
    return getattr(GenAIAttributes, name, fallback)


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
GEN_AI_RESPONSE_MODEL = _attr("GEN_AI_RESPONSE_MODEL", "gen_ai.response.model")
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
GEN_AI_DATA_SOURCE_ID = _attr("GEN_AI_DATA_SOURCE_ID", "gen_ai.data_source.id")

# The semantic conventions currently expose multiple usage token attributes; we retain the
# completion/prompt aliases for backwards compatibility where used.
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
GEN_AI_TOKEN_TYPE = _attr("GEN_AI_TOKEN_TYPE", "gen_ai.token.type")


__all__ = [
    name for name in globals() if name.isupper() or name.startswith("GenAI")
]
