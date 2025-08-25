from os import environ
from typing import Optional

OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT = (
    "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT"
)
OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS = (
    "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS"
)
OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_DEFINITIONS = (
    "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_DEFINITIONS"
)
OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_IO = (
    "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_IO"
)
OTEL_INSTRUMENTATION_OPENAI_AGENTS_MAX_VALUE_LENGTH = (
    "OTEL_INSTRUMENTATION_OPENAI_AGENTS_MAX_VALUE_LENGTH"
)


def _is_true(var_name: str, default: str = "false") -> bool:
    return environ.get(var_name, default).lower() == "true"


def is_content_enabled() -> bool:
    return _is_true(OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT)


def is_metrics_enabled() -> bool:
    return _is_true(
        OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS, default="true"
    )


def is_tool_definitions_enabled() -> bool:
    return _is_true(
        OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_DEFINITIONS
    )


def is_tool_io_enabled() -> bool:
    return _is_true(OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_TOOL_IO)


def get_max_value_length() -> int:
    try:
        return int(
            environ.get(
                OTEL_INSTRUMENTATION_OPENAI_AGENTS_MAX_VALUE_LENGTH, "20480"
            )
        )
    except ValueError:
        return 20480


def get_agent_operation_name(operation: str) -> str:
    return f"openai_agents.{operation}"


def get_agent_span_name(operation: str, model: Optional[str] = None) -> str:
    if model:
        return f"openai_agents {operation} {model}"
    return f"openai_agents {operation}"
