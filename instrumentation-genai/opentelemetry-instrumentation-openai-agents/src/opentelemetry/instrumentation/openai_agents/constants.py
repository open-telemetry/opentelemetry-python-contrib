"""Centralized semantic convention constants for GenAI instrumentation.

Consolidates provider names, operation names, tool types, output types,
evaluation attributes, and helper maps so other modules can import from
one place. Keeping strings in one module reduces drift as the spec evolves.
"""

from __future__ import annotations


# Provider names (superset for forward compatibility)
class GenAIProvider:
    OPENAI = "openai"
    GCP_GEN_AI = "gcp.gen_ai"
    GCP_VERTEX_AI = "gcp.vertex_ai"
    GCP_GEMINI = "gcp.gemini"
    ANTHROPIC = "anthropic"
    COHERE = "cohere"
    AZURE_AI_INFERENCE = "azure.ai.inference"
    AZURE_AI_OPENAI = "azure.ai.openai"
    IBM_WATSONX_AI = "ibm.watsonx.ai"
    AWS_BEDROCK = "aws.bedrock"
    PERPLEXITY = "perplexity"
    X_AI = "x_ai"
    DEEPSEEK = "deepseek"
    GROQ = "groq"
    MISTRAL_AI = "mistral_ai"

    ALL = {
        OPENAI,
        GCP_GEN_AI,
        GCP_VERTEX_AI,
        GCP_GEMINI,
        ANTHROPIC,
        COHERE,
        AZURE_AI_INFERENCE,
        AZURE_AI_OPENAI,
        IBM_WATSONX_AI,
        AWS_BEDROCK,
        PERPLEXITY,
        X_AI,
        DEEPSEEK,
        GROQ,
        MISTRAL_AI,
    }


class GenAIOperationName:
    CHAT = "chat"
    GENERATE_CONTENT = "generate_content"
    TEXT_COMPLETION = "text_completion"
    EMBEDDINGS = "embeddings"
    CREATE_AGENT = "create_agent"
    INVOKE_AGENT = "invoke_agent"
    EXECUTE_TOOL = "execute_tool"
    TRANSCRIPTION = "transcription"
    SPEECH = "speech_generation"
    GUARDRAIL = "guardrail_check"
    HANDOFF = "agent_handoff"
    RESPONSE = "response"  # internal aggregator in current processor

    # Mapping of span data class (lower) to default op (heuristic)
    CLASS_FALLBACK = {
        "generationspan": CHAT,
        "responsespan": RESPONSE,
        "functionspan": EXECUTE_TOOL,
        "agentspan": INVOKE_AGENT,
    }


class GenAIOutputType:
    TEXT = "text"
    JSON = "json"
    IMAGE = "image"
    SPEECH = "speech"
    # existing custom inference types retained for backward compatibility


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


# Complete list of GenAI semantic convention attribute keys
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_REQUEST_TOP_P = "gen_ai.request.top_p"
GEN_AI_REQUEST_TOP_K = "gen_ai.request.top_k"
GEN_AI_REQUEST_FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
GEN_AI_REQUEST_PRESENCE_PENALTY = "gen_ai.request.presence_penalty"
GEN_AI_REQUEST_CHOICE_COUNT = "gen_ai.request.choice.count"
GEN_AI_REQUEST_STOP_SEQUENCES = "gen_ai.request.stop_sequences"
GEN_AI_REQUEST_ENCODING_FORMATS = "gen_ai.request.encoding_formats"
GEN_AI_REQUEST_SEED = "gen_ai.request.seed"
GEN_AI_RESPONSE_ID = "gen_ai.response.id"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"
GEN_AI_CONVERSATION_ID = "gen_ai.conversation.id"
GEN_AI_AGENT_ID = "gen_ai.agent.id"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_AGENT_DESCRIPTION = "gen_ai.agent.description"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_TYPE = "gen_ai.tool.type"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
GEN_AI_TOOL_DESCRIPTION = "gen_ai.tool.description"
GEN_AI_TOOL_CALL_ARGUMENTS = "gen_ai.tool.call.arguments"
GEN_AI_TOOL_CALL_RESULT = "gen_ai.tool.call.result"
GEN_AI_TOOL_DEFINITIONS = "gen_ai.tool.definitions"
GEN_AI_ORCHESTRATOR_AGENT_DEFINITIONS = "gen_ai.orchestrator.agent.definitions"
GEN_AI_OUTPUT_TYPE = "gen_ai.output.type"
GEN_AI_SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"
GEN_AI_INPUT_MESSAGES = "gen_ai.input.messages"
GEN_AI_OUTPUT_MESSAGES = "gen_ai.output.messages"
GEN_AI_GUARDRAIL_NAME = "gen_ai.guardrail.name"
GEN_AI_GUARDRAIL_TRIGGERED = "gen_ai.guardrail.triggered"
GEN_AI_HANDOFF_FROM_AGENT = "gen_ai.handoff.from_agent"
GEN_AI_HANDOFF_TO_AGENT = "gen_ai.handoff.to_agent"
GEN_AI_EMBEDDINGS_DIMENSION_COUNT = "gen_ai.embeddings.dimension.count"
GEN_AI_DATA_SOURCE_ID = "gen_ai.data_source.id"
