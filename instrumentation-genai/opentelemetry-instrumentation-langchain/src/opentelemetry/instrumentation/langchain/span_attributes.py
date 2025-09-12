"""
Semantic conventions for Gen AI agent spans following OpenTelemetry standards.

This module defines constants for span attribute names as specified in:
https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-agent-spans.md
"""

class Span_Attributes:
    GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
    GEN_AI_SYSTEM = "gen_ai.system"
    GEN_AI_ERROR_TYPE = "error.type"
    GEN_AI_AGENT_DESCRIPTION = "gen_ai.agent.description"
    GEN_AI_AGENT_ID = "gen_ai.agent.id"
    GEN_AI_AGENT_NAME = "gen_ai.agent.name"
    GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
    GEN_AI_SERVER_PORT = "server.port"
    GEN_AI_REQUEST_FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
    GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
    GEN_AI_REQUEST_PRESENCE_PENALTY = "gen_ai.request.presence_penalty"
    GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
    GEN_AI_REQUEST_TOP_P = "gen_ai.request.top_p"
    GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
    GEN_AI_RESPONSE_ID = "gen_ai.response.id"
    GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
    GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
    GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
    GEN_AI_SERVER_ADDR = "server.address"
    GEN_AI_TOOL_CALL_ID= "gen_ai.tool.call.id"
    GEN_AI_TOOL_NAME = "gen_ai.tool.name"
    GEN_AI_TOOL_DESCRIPTION = "gen_ai.tool.description"
    GEN_AI_TOOL_TYPE = "gen_ai.tool.type"
    
    
class GenAIOperationValues:
    CHAT = "chat"
    CREATE_AGENT = "create_agent"
    EMBEDDINGS = "embeddings"
    GENERATE_CONTENT = "generate_content"
    INVOKE_AGENT = "invoke_agent"
    TEXT_COMPLETION = "text_completion"
    UNKNOWN = "unknown"