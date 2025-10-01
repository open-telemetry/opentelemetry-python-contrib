"""
Centralized constants for GenAI telemetry attribute names.
This module replaces inline string literals for span & event attributes.
"""

# Semantic attribute names for core GenAI spans/events
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_INPUT_MESSAGES = "gen_ai.input.messages"
GEN_AI_OUTPUT_MESSAGES = "gen_ai.output.messages"
GEN_AI_FRAMEWORK = "gen_ai.framework"
GEN_AI_COMPLETION_PREFIX = "gen_ai.completion"

# Additional semantic attribute constants
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_ID = "gen_ai.response.id"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_EVALUATION_NAME = "gen_ai.evaluation.name"
GEN_AI_EVALUATION_SCORE_VALUE = "gen_ai.evaluation.score.value"
GEN_AI_EVALUATION_SCORE_LABEL = "gen_ai.evaluation.score.label"
GEN_AI_EVALUATION_EXPLANATION = "gen_ai.evaluation.explanation"

# Agent attributes (from semantic conventions)
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_AGENT_ID = "gen_ai.agent.id"
GEN_AI_AGENT_DESCRIPTION = "gen_ai.agent.description"
GEN_AI_AGENT_TOOLS = "gen_ai.agent.tools"
GEN_AI_AGENT_TYPE = "gen_ai.agent.type"
GEN_AI_AGENT_SYSTEM_INSTRUCTIONS = "gen_ai.agent.system_instructions"
GEN_AI_AGENT_INPUT_CONTEXT = "gen_ai.agent.input_context"
GEN_AI_AGENT_OUTPUT_RESULT = "gen_ai.agent.output_result"

# Workflow attributes (not in semantic conventions)
GEN_AI_WORKFLOW_NAME = "gen_ai.workflow.name"
GEN_AI_WORKFLOW_TYPE = "gen_ai.workflow.type"
GEN_AI_WORKFLOW_DESCRIPTION = "gen_ai.workflow.description"
GEN_AI_WORKFLOW_INITIAL_INPUT = "gen_ai.workflow.initial_input"
GEN_AI_WORKFLOW_FINAL_OUTPUT = "gen_ai.workflow.final_output"

# Task attributes (not in semantic conventions)
GEN_AI_TASK_NAME = "gen_ai.task.name"
GEN_AI_TASK_TYPE = "gen_ai.task.type"
GEN_AI_TASK_OBJECTIVE = "gen_ai.task.objective"
GEN_AI_TASK_SOURCE = "gen_ai.task.source"
GEN_AI_TASK_ASSIGNED_AGENT = "gen_ai.task.assigned_agent"
GEN_AI_TASK_STATUS = "gen_ai.task.status"
GEN_AI_TASK_INPUT_DATA = "gen_ai.task.input_data"
GEN_AI_TASK_OUTPUT_DATA = "gen_ai.task.output_data"
