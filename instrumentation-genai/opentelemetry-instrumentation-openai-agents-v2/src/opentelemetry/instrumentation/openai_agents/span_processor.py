"""
GenAI Semantic Convention Trace Processor

This module implements a custom trace processor that enriches spans with
OpenTelemetry GenAI semantic conventions attributes following the
OpenInference processor pattern. It adds standardized attributes for
generative AI operations using iterator-based attribute extraction.

References:
- OpenTelemetry GenAI Semantic Conventions:
    https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
- OpenInference Pattern: https://github.com/Arize-ai/openinference
"""

# pylint: disable=too-many-lines,invalid-name,too-many-locals,too-many-branches,too-many-statements,too-many-return-statements,too-many-nested-blocks,too-many-arguments,too-many-instance-attributes,broad-exception-caught,no-self-use,consider-iterating-dictionary,unused-variable,unnecessary-pass

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Iterator, Optional, Sequence
from urllib.parse import urlparse

from opentelemetry.util.genai.utils import gen_ai_json_dumps

try:
    from agents.tracing import Span, Trace, TracingProcessor
    from agents.tracing.span_data import (
        AgentSpanData,
        FunctionSpanData,
        GenerationSpanData,
        GuardrailSpanData,
        HandoffSpanData,
        ResponseSpanData,
        SpeechSpanData,
        TranscriptionSpanData,
    )
except ModuleNotFoundError:  # pragma: no cover - test stubs
    tracing_module = importlib.import_module("agents.tracing")
    Span = getattr(tracing_module, "Span")
    Trace = getattr(tracing_module, "Trace")
    TracingProcessor = getattr(tracing_module, "TracingProcessor")
    AgentSpanData = getattr(tracing_module, "AgentSpanData", Any)  # type: ignore[assignment]
    FunctionSpanData = getattr(tracing_module, "FunctionSpanData", Any)  # type: ignore[assignment]
    GenerationSpanData = getattr(tracing_module, "GenerationSpanData", Any)  # type: ignore[assignment]
    GuardrailSpanData = getattr(tracing_module, "GuardrailSpanData", Any)  # type: ignore[assignment]
    HandoffSpanData = getattr(tracing_module, "HandoffSpanData", Any)  # type: ignore[assignment]
    ResponseSpanData = getattr(tracing_module, "ResponseSpanData", Any)  # type: ignore[assignment]
    SpeechSpanData = getattr(tracing_module, "SpeechSpanData", Any)  # type: ignore[assignment]
    TranscriptionSpanData = getattr(
        tracing_module, "TranscriptionSpanData", Any
    )  # type: ignore[assignment]

from opentelemetry.context import attach, detach
from opentelemetry.metrics import Histogram, get_meter
from opentelemetry.semconv._incubating.attributes import (
    gen_ai_attributes as GenAIAttributes,
)
from opentelemetry.semconv._incubating.attributes import (
    server_attributes as ServerAttributes,
)
from opentelemetry.trace import Span as OtelSpan
from opentelemetry.trace import (
    SpanKind,
    Status,
    StatusCode,
    Tracer,
    set_span_in_context,
)
from opentelemetry.util.types import AttributeValue

# Import all semantic convention constants
# ---- GenAI semantic convention helpers (embedded from constants.py) ----


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

# ---- Normalization utilities (embedded from utils.py) ----


def normalize_provider(provider: Optional[str]) -> Optional[str]:
    """Normalize provider name to spec-compliant value."""
    if not provider:
        return None
    normalized = provider.strip().lower()
    if normalized in GenAIProvider.ALL:
        return normalized
    return provider  # passthrough if unknown (forward compat)


def validate_tool_type(tool_type: Optional[str]) -> str:
    """Validate and normalize tool type."""
    if not tool_type:
        return GenAIToolType.FUNCTION  # default
    normalized = tool_type.strip().lower()
    return (
        normalized
        if normalized in GenAIToolType.ALL
        else GenAIToolType.FUNCTION
    )


def normalize_output_type(output_type: Optional[str]) -> str:
    """Normalize output type to spec-compliant value."""
    if not output_type:
        return GenAIOutputType.TEXT  # default
    normalized = output_type.strip().lower()
    base_map = {
        "json_object": GenAIOutputType.JSON,
        "jsonschema": GenAIOutputType.JSON,
        "speech_audio": GenAIOutputType.SPEECH,
        "audio_speech": GenAIOutputType.SPEECH,
        "image_png": GenAIOutputType.IMAGE,
        "function_arguments_json": GenAIOutputType.JSON,
        "tool_call": GenAIOutputType.JSON,
        "transcription_json": GenAIOutputType.JSON,
    }
    if normalized in base_map:
        return base_map[normalized]
    if normalized in {
        GenAIOutputType.TEXT,
        GenAIOutputType.JSON,
        GenAIOutputType.IMAGE,
        GenAIOutputType.SPEECH,
    }:
        return normalized
    return GenAIOutputType.TEXT  # default for unknown


if TYPE_CHECKING:
    pass

# Legacy attributes removed

logger = logging.getLogger(__name__)

GEN_AI_SYSTEM_KEY = getattr(GenAIAttributes, "GEN_AI_SYSTEM", "gen_ai.system")


class ContentCaptureMode(Enum):
    """Controls whether sensitive content is recorded on spans, events, or both."""

    NO_CONTENT = "no_content"
    SPAN_ONLY = "span_only"
    EVENT_ONLY = "event_only"
    SPAN_AND_EVENT = "span_and_event"

    @property
    def capture_in_span(self) -> bool:
        return self in (
            ContentCaptureMode.SPAN_ONLY,
            ContentCaptureMode.SPAN_AND_EVENT,
        )

    @property
    def capture_in_event(self) -> bool:
        return self in (
            ContentCaptureMode.EVENT_ONLY,
            ContentCaptureMode.SPAN_AND_EVENT,
        )


@dataclass
class ContentPayload:
    """Container for normalized content associated with a span."""

    input_messages: Optional[list[dict[str, Any]]] = None
    output_messages: Optional[list[dict[str, Any]]] = None
    system_instructions: Optional[list[dict[str, str]]] = None
    tool_arguments: Any = None
    tool_result: Any = None


def _is_instance_of(value: Any, classes: Any) -> bool:
    """Safe isinstance that tolerates typing.Any placeholders."""
    if not isinstance(classes, tuple):
        classes = (classes,)
    for cls in classes:
        try:
            if isinstance(value, cls):
                return True
        except TypeError:
            continue
    return False


def _infer_server_attributes(base_url: Optional[str]) -> dict[str, Any]:
    """Return server.address / server.port attributes if base_url provided."""
    out: dict[str, Any] = {}
    if not base_url:
        return out
    try:
        parsed = urlparse(base_url)
        if parsed.hostname:
            out[ServerAttributes.SERVER_ADDRESS] = parsed.hostname
        if parsed.port:
            out[ServerAttributes.SERVER_PORT] = parsed.port
    except Exception:
        return out
    return out


def safe_json_dumps(obj: Any) -> str:
    """Safely convert object to JSON string (fallback to str)."""
    try:
        return gen_ai_json_dumps(obj)
    except (TypeError, ValueError) as e:
        logger.warning("Failed to serialize object to JSON: %s", e)
        return str(obj)


def safe_json_loads(s: str) -> Any:
    """Safely parse JSON string (fallback to original string)."""
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse JSON string: %s", e)
        return s


def _as_utc_nano(dt: datetime) -> int:
    """Convert datetime to UTC nanoseconds timestamp."""
    return int(dt.astimezone(timezone.utc).timestamp() * 1_000_000_000)


def _get_span_status(span: Span[Any]) -> Status:
    """Get OpenTelemetry span status from agent span."""
    if error := getattr(span, "error", None):
        return Status(
            status_code=StatusCode.ERROR,
            description=f"{error.get('message', '')}: {error.get('data', '')}",
        )
    return Status(StatusCode.OK)


def get_span_name(
    operation_name: str,
    model: Optional[str] = None,
    agent_name: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> str:
    """Generate spec-compliant span name based on operation type."""
    base_name = operation_name

    if operation_name in {
        GenAIOperationName.CHAT,
        GenAIOperationName.TEXT_COMPLETION,
        GenAIOperationName.EMBEDDINGS,
        GenAIOperationName.TRANSCRIPTION,
        GenAIOperationName.SPEECH,
    }:
        return f"{base_name} {model}" if model else base_name

    if operation_name == GenAIOperationName.CREATE_AGENT:
        return f"{base_name} {agent_name}" if agent_name else base_name

    if operation_name == GenAIOperationName.INVOKE_AGENT:
        return f"{base_name} {agent_name}" if agent_name else base_name

    if operation_name == GenAIOperationName.EXECUTE_TOOL:
        return f"{base_name} {tool_name}" if tool_name else base_name

    if operation_name == GenAIOperationName.HANDOFF:
        return f"{base_name} {agent_name}" if agent_name else base_name

    return base_name


class GenAISemanticProcessor(TracingProcessor):
    """Trace processor adding GenAI semantic convention attributes with metrics."""

    def __init__(
        self,
        tracer: Optional[Tracer] = None,
        system_name: str = "openai",
        include_sensitive_data: bool = True,
        content_mode: ContentCaptureMode = ContentCaptureMode.SPAN_AND_EVENT,
        base_url: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_description: Optional[str] = None,
        server_address: Optional[str] = None,
        server_port: Optional[int] = None,
        metrics_enabled: bool = True,
        agent_name_default: Optional[str] = None,
        agent_id_default: Optional[str] = None,
        agent_description_default: Optional[str] = None,
        base_url_default: Optional[str] = None,
        server_address_default: Optional[str] = None,
        server_port_default: Optional[int] = None,
    ):
        """Initialize processor with metrics support.

        Args:
            tracer: Optional OpenTelemetry tracer
            system_name: Provider name (openai/azure.ai.inference/etc.)
            include_sensitive_data: Include model/tool IO when True
            base_url: API endpoint for server.address/port
            agent_name: Name of the agent (can be overridden by env var)
            agent_id: ID of the agent (can be overridden by env var)
            agent_description: Description of the agent (can be overridden by env var)
            server_address: Server address (can be overridden by env var or base_url)
            server_port: Server port (can be overridden by env var or base_url)
        """
        self._tracer = tracer
        self.system_name = normalize_provider(system_name) or system_name
        self._content_mode = content_mode
        self.include_sensitive_data = include_sensitive_data and (
            content_mode.capture_in_span or content_mode.capture_in_event
        )
        effective_base_url = base_url or base_url_default
        self.base_url = effective_base_url

        # Agent information - prefer explicit overrides; otherwise defer to span data
        self.agent_name = agent_name
        self.agent_id = agent_id
        self.agent_description = agent_description
        self._agent_name_default = agent_name_default
        self._agent_id_default = agent_id_default
        self._agent_description_default = agent_description_default

        # Server information - use init parameters, then base_url inference
        self.server_address = server_address or server_address_default
        resolved_port = (
            server_port if server_port is not None else server_port_default
        )
        self.server_port = resolved_port

        # If server info not provided, try to extract from base_url
        if (
            not self.server_address or not self.server_port
        ) and effective_base_url:
            server_attrs = _infer_server_attributes(effective_base_url)
            if not self.server_address:
                self.server_address = server_attrs.get(
                    ServerAttributes.SERVER_ADDRESS
                )
            if not self.server_port:
                self.server_port = server_attrs.get(
                    ServerAttributes.SERVER_PORT
                )

        # Content capture configuration
        self._capture_messages = (
            content_mode.capture_in_span or content_mode.capture_in_event
        )
        self._capture_system_instructions = True
        self._capture_tool_definitions = True

        # Span tracking
        self._root_spans: dict[str, OtelSpan] = {}
        self._otel_spans: dict[str, OtelSpan] = {}
        self._tokens: dict[str, object] = {}
        self._span_parents: dict[str, Optional[str]] = {}
        self._agent_content: dict[str, Dict[str, list[Any]]] = {}

        # Metrics configuration
        self._metrics_enabled = metrics_enabled
        self._meter = None
        self._duration_histogram: Optional[Histogram] = None
        self._token_usage_histogram: Optional[Histogram] = None
        if self._metrics_enabled:
            self._init_metrics()

    def _get_server_attributes(self) -> dict[str, Any]:
        """Get server attributes from configured values."""
        attrs = {}
        if self.server_address:
            attrs[ServerAttributes.SERVER_ADDRESS] = self.server_address
        if self.server_port:
            attrs[ServerAttributes.SERVER_PORT] = self.server_port
        return attrs

    def _init_metrics(self):
        """Initialize metric instruments."""
        self._meter = get_meter(
            "opentelemetry.instrumentation.openai_agents", "0.1.0"
        )

        # Operation duration histogram
        self._duration_histogram = self._meter.create_histogram(
            name="gen_ai.client.operation.duration",
            description="GenAI operation duration",
            unit="s",
        )

        # Token usage histogram
        self._token_usage_histogram = self._meter.create_histogram(
            name="gen_ai.client.token.usage",
            description="Number of input and output tokens used",
            unit="{token}",
        )

    def _record_metrics(
        self, span: Span[Any], attributes: dict[str, AttributeValue]
    ) -> None:
        """Record metrics for the span."""
        if not self._metrics_enabled or (
            self._duration_histogram is None
            and self._token_usage_histogram is None
        ):
            return

        try:
            # Calculate duration
            duration = None
            if hasattr(span, "started_at") and hasattr(span, "ended_at"):
                try:
                    start = datetime.fromisoformat(span.started_at)
                    end = datetime.fromisoformat(span.ended_at)
                    duration = (end - start).total_seconds()
                except Exception:
                    pass

            # Build metric attributes
            metric_attrs = {
                GEN_AI_PROVIDER_NAME: attributes.get(GEN_AI_PROVIDER_NAME),
                GEN_AI_OPERATION_NAME: attributes.get(GEN_AI_OPERATION_NAME),
                GEN_AI_REQUEST_MODEL: (
                    attributes.get(GEN_AI_REQUEST_MODEL)
                    or attributes.get(GEN_AI_RESPONSE_MODEL)
                ),
                ServerAttributes.SERVER_ADDRESS: attributes.get(
                    ServerAttributes.SERVER_ADDRESS
                ),
                ServerAttributes.SERVER_PORT: attributes.get(
                    ServerAttributes.SERVER_PORT
                ),
            }

            # Add error type if present
            if error := getattr(span, "error", None):
                error_type = error.get("type") or error.get("name")
                if error_type:
                    metric_attrs["error.type"] = error_type

            # Remove None values
            metric_attrs = {
                k: v for k, v in metric_attrs.items() if v is not None
            }

            # Record duration
            if duration is not None and self._duration_histogram is not None:
                self._duration_histogram.record(duration, metric_attrs)

            # Record token usage
            if self._token_usage_histogram:
                input_tokens = attributes.get(GEN_AI_USAGE_INPUT_TOKENS)
                if isinstance(input_tokens, (int, float)):
                    token_attrs = dict(metric_attrs)
                    token_attrs[GEN_AI_TOKEN_TYPE] = "input"
                    self._token_usage_histogram.record(
                        input_tokens, token_attrs
                    )

                output_tokens = attributes.get(GEN_AI_USAGE_OUTPUT_TOKENS)
                if isinstance(output_tokens, (int, float)):
                    token_attrs = dict(metric_attrs)
                    token_attrs[GEN_AI_TOKEN_TYPE] = "output"
                    self._token_usage_histogram.record(
                        output_tokens, token_attrs
                    )

        except Exception as e:
            logger.debug("Failed to record metrics: %s", e)

    def _emit_content_events(
        self,
        span: Span[Any],
        otel_span: OtelSpan,
        payload: ContentPayload,
        agent_content: Optional[Dict[str, list[Any]]] = None,
    ) -> None:
        """Intentionally skip emitting gen_ai.* events to avoid payload duplication."""
        if (
            not self.include_sensitive_data
            or not self._content_mode.capture_in_event
            or not otel_span.is_recording()
        ):
            return

        logger.debug(
            "Event capture requested for span %s but is currently disabled",
            getattr(span, "span_id", "<unknown>"),
        )
        return

    def _collect_system_instructions(
        self, messages: Sequence[Any] | None
    ) -> list[dict[str, str]]:
        """Return system/ai role instructions as typed text objects.

        Enforces format: [{"type": "text", "content": "..."}].
        Handles message content that may be a string, list of parts,
        or a dict with text/content fields.
        """
        if not messages:
            return []
        out: list[dict[str, str]] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            if role in {"system", "ai"}:
                content = m.get("content")
                out.extend(self._normalize_to_text_parts(content))
        return out

    def _normalize_to_text_parts(self, content: Any) -> list[dict[str, str]]:
        """Normalize arbitrary content into typed text parts.

        - String -> [{type: text, content: <string>}]
        - List/Tuple -> map each item to a text part (string/dict supported)
        - Dict -> use 'text' or 'content' field when available; else str(dict)
        - Other -> str(value)
        """
        parts: list[dict[str, str]] = []
        if content is None:
            return parts
        if isinstance(content, str):
            parts.append({"type": "text", "content": content})
            return parts
        if isinstance(content, (list, tuple)):
            for item in content:
                if isinstance(item, str):
                    parts.append({"type": "text", "content": item})
                elif isinstance(item, dict):
                    txt = item.get("text") or item.get("content")
                    if isinstance(txt, str) and txt:
                        parts.append({"type": "text", "content": txt})
                    else:
                        parts.append({"type": "text", "content": str(item)})
                else:
                    parts.append({"type": "text", "content": str(item)})
            return parts
        if isinstance(content, dict):
            txt = content.get("text") or content.get("content")
            if isinstance(txt, str) and txt:
                parts.append({"type": "text", "content": txt})
            else:
                parts.append({"type": "text", "content": str(content)})
            return parts
        # Fallback for other types
        parts.append({"type": "text", "content": str(content)})
        return parts

    def _redacted_text_parts(self) -> list[dict[str, str]]:
        """Return a single redacted text part for system instructions."""
        return [{"type": "text", "content": "readacted"}]

    def _normalize_messages_to_role_parts(
        self, messages: Sequence[Any] | None
    ) -> list[dict[str, Any]]:
        """Normalize input messages to enforced role+parts schema.

        Each message becomes: {"role": <role>, "parts": [ {"type": ..., ...} ]}
        Redaction: when include_sensitive_data is False, replace text content,
        tool_call arguments, and tool_call_response result with "readacted".
        """
        if not messages:
            return []
        normalized: list[dict[str, Any]] = []
        for m in messages:
            if not isinstance(m, dict):
                # Fallback: treat as user text
                normalized.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "type": "text",
                                "content": "readacted"
                                if not self.include_sensitive_data
                                else str(m),
                            }
                        ],
                    }
                )
                continue

            role = m.get("role") or "user"
            parts: list[dict[str, Any]] = []

            # Existing parts array
            if isinstance(m.get("parts"), (list, tuple)):
                for p in m["parts"]:
                    if isinstance(p, dict):
                        ptype = p.get("type") or "text"
                        newp: dict[str, Any] = {"type": ptype}
                        if ptype == "text":
                            txt = p.get("content") or p.get("text")
                            newp["content"] = (
                                "readacted"
                                if not self.include_sensitive_data
                                else (txt if isinstance(txt, str) else str(p))
                            )
                        elif ptype == "tool_call":
                            newp["id"] = p.get("id")
                            newp["name"] = p.get("name")
                            args = p.get("arguments")
                            newp["arguments"] = (
                                "readacted"
                                if not self.include_sensitive_data
                                else args
                            )
                        elif ptype == "tool_call_response":
                            newp["id"] = p.get("id") or m.get("tool_call_id")
                            result = p.get("result") or p.get("content")
                            newp["result"] = (
                                "readacted"
                                if not self.include_sensitive_data
                                else result
                            )
                        else:
                            newp["content"] = (
                                "readacted"
                                if not self.include_sensitive_data
                                else str(p)
                            )
                        parts.append(newp)
                    else:
                        parts.append(
                            {
                                "type": "text",
                                "content": "readacted"
                                if not self.include_sensitive_data
                                else str(p),
                            }
                        )

            # OpenAI content
            content = m.get("content")
            if isinstance(content, str):
                parts.append(
                    {
                        "type": "text",
                        "content": "readacted"
                        if not self.include_sensitive_data
                        else content,
                    }
                )
            elif isinstance(content, (list, tuple)):
                for item in content:
                    if isinstance(item, dict):
                        itype = item.get("type") or "text"
                        if itype == "text":
                            txt = item.get("text") or item.get("content")
                            parts.append(
                                {
                                    "type": "text",
                                    "content": "readacted"
                                    if not self.include_sensitive_data
                                    else (
                                        txt
                                        if isinstance(txt, str)
                                        else str(item)
                                    ),
                                }
                            )
                        else:
                            # Fallback for other part types
                            parts.append(
                                {
                                    "type": "text",
                                    "content": "readacted"
                                    if not self.include_sensitive_data
                                    else str(item),
                                }
                            )
                    else:
                        parts.append(
                            {
                                "type": "text",
                                "content": "readacted"
                                if not self.include_sensitive_data
                                else str(item),
                            }
                        )

            # Assistant tool_calls
            if role == "assistant" and isinstance(
                m.get("tool_calls"), (list, tuple)
            ):
                for tc in m["tool_calls"]:
                    if not isinstance(tc, dict):
                        continue
                    p = {"type": "tool_call"}
                    p["id"] = tc.get("id")
                    fn = tc.get("function") or {}
                    if isinstance(fn, dict):
                        p["name"] = fn.get("name")
                        args = fn.get("arguments")
                        p["arguments"] = (
                            "readacted"
                            if not self.include_sensitive_data
                            else args
                        )
                    parts.append(p)

            # Tool call response
            if role in {"tool", "function"}:
                p = {"type": "tool_call_response"}
                p["id"] = m.get("tool_call_id") or m.get("id")
                result = m.get("result") or m.get("content")
                p["result"] = (
                    "readacted" if not self.include_sensitive_data else result
                )
                parts.append(p)

            if parts:
                normalized.append({"role": role, "parts": parts})
            elif not self.include_sensitive_data:
                normalized.append(
                    {"role": role, "parts": self._redacted_text_parts()}
                )

        return normalized

    def _normalize_response_output_part(
        self, item: Any
    ) -> list[dict[str, Any]]:
        part_type = getattr(item, "type", None)
        if part_type == "message":  # ResponseOutputMessage
            parts = []
            content = getattr(item, "content", None)
            if isinstance(content, Sequence):
                for c in content:
                    content_type = getattr(c, "type", None)
                    if content_type == "output_text":
                        parts.append(
                            {
                                "type": "text",
                                "annotations": (  # out of spec but useful
                                    ["readacted"]
                                    if not self.include_sensitive_data
                                    else [
                                        a.to_dict()
                                        if hasattr(a, "to_dict")
                                        else str(a)
                                        for a in getattr(c, "annotations", [])
                                    ]
                                ),
                                "content": (
                                    "readacted"
                                    if not self.include_sensitive_data
                                    else getattr(c, "text", None)
                                ),
                            }
                        )
                    elif content_type == "refusal":
                        parts.append(
                            {
                                "type": "refusal",  # custom type
                                "content": (
                                    "readacted"
                                    if not self.include_sensitive_data
                                    else getattr(c, "refusal", None)
                                ),
                            }
                        )
            else:
                parts.append(
                    {
                        "type": "text",
                        "content": (
                            "readacted"
                            if not self.include_sensitive_data
                            else str(content)
                        ),
                    }
                )
            return parts
        if part_type == "file_search_call":  # ResponseFileSearchToolCall
            return [
                {
                    "type": "tool_call",
                    "name": "file_search",
                    "id": getattr(item, "id", None),
                    "arguments": (
                        {
                            "queries": (
                                ["readacted"]
                                if not self.include_sensitive_data
                                else getattr(item, "queries", [])
                            )
                        }
                    ),
                }
            ]
        elif part_type == "function_call":  # ResponseFunctionToolCall
            return [
                {
                    "type": "tool_call",
                    "name": getattr(item, "name", None),
                    "id": getattr(item, "id", None),
                    "arguments": (
                        "readacted"
                        if not self.include_sensitive_data
                        else safe_json_loads(getattr(item, "arguments", None))
                    ),
                }
            ]
        elif part_type == "web_search_call":  # ResponseFunctionWebSearch
            action = getattr(item, "action", None)
            action_type = getattr(action, "type", None)
            action_obj = (
                {"type": action_type}
                if not self.include_sensitive_data
                else action.to_dict()
                if hasattr(action, "to_dict")
                else str(action)
            )
            return [
                {
                    "type": "tool_call",
                    "name": "web_search",
                    "id": getattr(item, "id", None),
                    "arguments": {
                        "action": action_obj,
                    },
                }
            ]
        elif part_type == "computer_call":  # ResponseComputerToolCall
            action = getattr(item, "action", None)
            action_type = getattr(action, "type", None)
            action_obj = (
                {"type": action_type}
                if not self.include_sensitive_data
                else action.to_dict()
                if hasattr(action, "to_dict")
                else str(action)
            )
            return [
                {
                    "type": "tool_call",
                    "name": "computer",
                    "id": getattr(item, "id", None),
                    "arguments": {
                        "action": action_obj,
                    },
                }
            ]
        elif part_type == "reasoning":  # ResponseReasoningItem
            content = getattr(item, "content", None)
            content_str = (
                str.join(
                    "\n",
                    [
                        getattr(c, "text", "")
                        if hasattr(c, "text")
                        else str(c)
                        for c in content
                    ],
                )
                if isinstance(content, Sequence)
                else str(content)
            )
            return [
                {
                    "type": "reasoning",
                    "content": (
                        "readacted"
                        if not self.include_sensitive_data
                        else content_str
                    ),
                }
            ]
        elif part_type == "compaction":  # ResponseCompactionItem
            return [
                {
                    "type": "compaction",  # custom type
                    "content": (
                        "readacted"
                        if not self.include_sensitive_data
                        else getattr(item, "encrypted_content", None)
                    ),
                }
            ]
        elif part_type == "image_generation_call":  # ImageGenerationCall
            return [
                {
                    "type": "tool_call_response",
                    "name": "image_generation",
                    "id": getattr(item, "id", None),
                    "response": {
                        "result": (
                            "readacted"
                            if not self.include_sensitive_data
                            else getattr(item, "result", None)
                        )
                    },
                }
            ]
        elif (
            part_type == "code_interpreter_call"
        ):  # ResponseCodeInterpreterToolCall
            return [
                {
                    "type": "tool_call",
                    "name": "code_interpreter",
                    "id": getattr(item, "id", None),
                    "arguments": {
                        "container_id": getattr(item, "container_id", None),
                        "code": (
                            "readacted"
                            if not self.include_sensitive_data
                            else getattr(item, "code", None)
                        ),
                    },
                },
                {
                    "type": "tool_call_response",
                    "name": "code_interpreter",
                    "id": getattr(item, "id", None),
                    "response": (
                        "readacted"
                        if not self.include_sensitive_data
                        else [
                            output.to_dict()
                            for output in getattr(item, "outputs", [])
                        ]
                    ),
                },
            ]
        elif part_type == "local_shell_call":  # LocalShellCall
            action = getattr(item, "action", None)
            return [
                {
                    "type": "tool_call",
                    "name": "local_shell",
                    "id": getattr(item, "id", None),
                    "arguments": {
                        "type": getattr(action, "type", None),
                        "timeout_ms": getattr(action, "timeout_ms", None),
                        "command": (
                            ["readacted"]
                            if not self.include_sensitive_data
                            else getattr(action, "command", None)
                        ),
                        "env": (
                            "readacted"
                            if not self.include_sensitive_data
                            else getattr(action, "env", None)
                        ),
                        "user": (
                            "readacted"
                            if not self.include_sensitive_data
                            else getattr(action, "user", None)
                        ),
                        "working_directory": (
                            "readacted"
                            if not self.include_sensitive_data
                            else getattr(action, "working_directory", None)
                        ),
                    },
                }
            ]
        elif part_type == "shell_call":  # ResponseFunctionShellToolCall
            action = getattr(item, "action", None)
            return [
                {
                    "type": "tool_call",
                    "name": "shell",
                    "id": getattr(item, "id", None),
                    "arguments": {
                        "created_by": getattr(action, "created_by", None),
                        "call_id": getattr(item, "call_id", None),
                        "environment": getattr(action, "environment", None),
                        "commands": (
                            ["readacted"]
                            if not self.include_sensitive_data
                            else getattr(action, "commands", None)
                        ),
                        "max_output_length": getattr(
                            action, "max_output_length", None
                        ),
                        "timeout_ms": getattr(action, "timeout_ms", None),
                    },
                }
            ]
        elif (
            part_type == "shell_call_output"
        ):  # ResponseFunctionShellToolCallOutput
            return [
                {
                    "type": "tool_call_response",
                    "name": "shell",
                    "id": getattr(item, "id", None),
                    "response": {
                        "created_by": getattr(item, "created_by", None),
                        "call_id": getattr(item, "call_id", None),
                        "result": (
                            ["readacted"]
                            if not self.include_sensitive_data
                            else [
                                output.to_dict()
                                for output in getattr(item, "output", [])
                            ]
                        ),
                    },
                }
            ]
        elif part_type == "apply_patch_call":  # ResponseApplyPatchToolCall
            operation = getattr(item, "operation", None)
            operation_type = getattr(operation, "type", None)
            return [
                {
                    "type": "tool_call",
                    "name": "apply_patch",
                    "id": getattr(item, "id", None),
                    "arguments": {
                        "created_by": getattr(item, "created_by", None),
                        "call_id": getattr(item, "call_id", None),
                        "operation": (
                            {"type": operation_type}
                            if not self.include_sensitive_data
                            else operation.to_dict()
                            if hasattr(operation, "to_dict")
                            else safe_json_dumps(operation)
                        ),
                    },
                }
            ]
        elif (
            part_type == "apply_patch_call_output"
        ):  # ResponseApplyPatchToolCallOutput
            return [
                {
                    "type": "tool_call_response",
                    "name": "apply_patch",
                    "id": getattr(item, "id", None),
                    "response": {
                        "created_by": getattr(item, "created_by", None),
                        "call_id": getattr(item, "call_id", None),
                        "status": getattr(item, "status", None),
                        "output": (
                            "readacted"
                            if not self.include_sensitive_data
                            else getattr(item, "output", None)
                        ),
                    },
                }
            ]
        elif part_type == "mcp_call":  # McpCall
            parts = [
                {
                    "type": "tool_call",
                    "name": "mcp_call",
                    "id": getattr(item, "id", None),
                    "arguments": {
                        "server": getattr(item, "server_label", None),
                        "tool_name": getattr(item, "name", None),
                        "tool_args": (
                            "readacted"
                            if not self.include_sensitive_data
                            else safe_json_loads(
                                getattr(item, "arguments", None)
                            )
                        ),
                    },
                }
            ]
            if getattr(item, "output", None) or getattr(item, "error", None):
                parts.append(
                    {
                        "type": "tool_call_response",
                        "name": "mcp_call",
                        "id": getattr(item, "id", None),
                        "response": {
                            "output": (
                                "readacted"
                                if not self.include_sensitive_data
                                else getattr(item, "output", None)
                            ),
                            "error": (
                                "readacted"
                                if not self.include_sensitive_data
                                else getattr(item, "error", None)
                            ),
                            "status": getattr(item, "status", None),
                        },
                    }
                )
            return parts
        elif part_type == "mcp_list_tools":  # McpListTools
            parts = [
                {
                    "type": "tool_call",
                    "name": "mcp_list_tools",
                    "id": getattr(item, "id", None),
                    "arguments": {
                        "server": getattr(item, "server_label", None),
                    },
                }
            ]
            if getattr(item, "tools", None) or getattr(item, "error", None):
                parts.append(
                    {
                        "type": "tool_call_response",
                        "name": "mcp_list_tools",
                        "id": getattr(item, "id", None),
                        "response": {
                            "tools": (
                                "readacted"
                                if not self.include_sensitive_data
                                else [
                                    tool.to_dict()
                                    for tool in getattr(item, "tools", [])
                                ]
                            ),
                            "error": (
                                "readacted"
                                if not self.include_sensitive_data
                                else getattr(item, "error", None)
                            ),
                        },
                    }
                )
            return parts
        elif part_type == "mcp_approval_request":  # McpApprovalRequest
            return [
                {
                    "type": "tool_call",
                    "name": "mcp_approval_request",
                    "id": getattr(item, "id", None),
                    "arguments": {
                        "server": getattr(item, "server_label", None),
                        "tool_name": getattr(item, "name", None),
                        "tool_args": (
                            "readacted"
                            if not self.include_sensitive_data
                            else safe_json_loads(
                                getattr(item, "arguments", None)
                            )
                        ),
                    },
                }
            ]
        elif part_type == "custom_tool_call":  # ResponseCustomToolCall
            return [
                {
                    "type": "tool_call",
                    "name": getattr(item, "name", None),
                    "id": getattr(item, "id", None),
                    "arguments": (
                        "readacted"
                        if not self.include_sensitive_data
                        else getattr(item, "input", None)
                    ),
                }
            ]

        # Fallback: content string attribute
        txt = getattr(item, "content", None)
        if isinstance(txt, str) and txt:
            return [
                {
                    "type": "text",
                    "content": (
                        "readacted" if not self.include_sensitive_data else txt
                    ),
                }
            ]
        else:
            # Fallback: stringified
            return [
                {
                    "type": "text",
                    "content": (
                        "readacted"
                        if not self.include_sensitive_data
                        else safe_json_dumps(item)
                    ),
                }
            ]

    def _normalize_output_messages_to_role_parts(
        self, span_data: Any
    ) -> list[dict[str, Any]]:
        """Normalize output messages to enforced role+parts schema.

        Produces: [{"role": "assistant", "parts": [{"type": "text", "content": "..."}],
                    optional "finish_reason": "..." }]
        """
        messages: list[dict[str, Any]] = []
        parts: list[dict[str, Any]] = []
        finish_reason: Optional[str] = None

        # Response span: use span_data.response.output, or fall back to consolidated output_text
        response = getattr(span_data, "response", None)
        if response is not None:
            output = getattr(response, "output", None)
            if isinstance(output, Sequence):
                for item in output:
                    parts.extend(self._normalize_response_output_part(item))

                    # Capture finish_reason from parts when present
                    fr = getattr(item, "finish_reason", None)
                    if isinstance(fr, str) and not finish_reason:
                        finish_reason = fr
            else:
                # Collect text content
                output_text = getattr(response, "output_text", None)
                if isinstance(output_text, str) and output_text:
                    parts.append(
                        {
                            "type": "text",
                            "content": (
                                "readacted"
                                if not self.include_sensitive_data
                                else output_text
                            ),
                        }
                    )

        # Generation span: use span_data.output
        if not parts:
            output = getattr(span_data, "output", None)
            if isinstance(output, Sequence):
                for item in output:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            txt = item.get("content") or item.get("text")
                            if isinstance(txt, str) and txt:
                                parts.append(
                                    {
                                        "type": "text",
                                        "content": (
                                            "readacted"
                                            if not self.include_sensitive_data
                                            else txt
                                        ),
                                    }
                                )
                        elif "content" in item and isinstance(
                            item["content"], str
                        ):
                            parts.append(
                                {
                                    "type": "text",
                                    "content": (
                                        "readacted"
                                        if not self.include_sensitive_data
                                        else item["content"]
                                    ),
                                }
                            )
                        else:
                            parts.append(
                                {
                                    "type": "text",
                                    "content": (
                                        "readacted"
                                        if not self.include_sensitive_data
                                        else str(item)
                                    ),
                                }
                            )
                        if not finish_reason and isinstance(
                            item.get("finish_reason"), str
                        ):
                            finish_reason = item.get("finish_reason")
                    elif isinstance(item, str):
                        parts.append(
                            {
                                "type": "text",
                                "content": (
                                    "readacted"
                                    if not self.include_sensitive_data
                                    else item
                                ),
                            }
                        )
                    else:
                        parts.append(
                            {
                                "type": "text",
                                "content": (
                                    "readacted"
                                    if not self.include_sensitive_data
                                    else str(item)
                                ),
                            }
                        )

        # Build assistant message
        msg: dict[str, Any] = {"role": "assistant", "parts": parts}
        if finish_reason:
            msg["finish_reason"] = finish_reason
        # Only include if there is content
        if parts:
            messages.append(msg)
        return messages

    def _build_content_payload(self, span: Span[Any]) -> ContentPayload:
        """Normalize content from span data for attribute/event capture."""
        payload = ContentPayload()
        span_data = getattr(span, "span_data", None)
        if span_data is None or not self.include_sensitive_data:
            return payload

        capture_messages = self._capture_messages and (
            self._content_mode.capture_in_span
            or self._content_mode.capture_in_event
        )
        capture_system = self._capture_system_instructions and (
            self._content_mode.capture_in_span
            or self._content_mode.capture_in_event
        )
        capture_tools = self._content_mode.capture_in_span or (
            self._content_mode.capture_in_event
            and _is_instance_of(span_data, FunctionSpanData)
        )

        if _is_instance_of(span_data, GenerationSpanData):
            span_input = getattr(span_data, "input", None)
            if capture_messages and span_input:
                payload.input_messages = (
                    self._normalize_messages_to_role_parts(span_input)
                )
            if capture_system and span_input:
                sys_instr = self._collect_system_instructions(span_input)
                if sys_instr:
                    payload.system_instructions = sys_instr
            if capture_messages and (
                getattr(span_data, "output", None)
                or getattr(span_data, "response", None)
            ):
                normalized_out = self._normalize_output_messages_to_role_parts(
                    span_data
                )
                if normalized_out:
                    payload.output_messages = normalized_out

        elif _is_instance_of(span_data, ResponseSpanData):
            span_input = getattr(span_data, "input", None)
            response_obj = getattr(span_data, "response", None)
            if capture_messages and span_input:
                payload.input_messages = (
                    self._normalize_messages_to_role_parts(span_input)
                )

            if (
                capture_system
                and response_obj
                and hasattr(response_obj, "instructions")
            ):
                payload.system_instructions = self._normalize_to_text_parts(
                    response_obj.instructions
                )
            if capture_system and span_input:
                sys_instr = self._collect_system_instructions(span_input)
                if sys_instr:
                    payload.system_instructions = sys_instr
            if capture_messages:
                normalized_out = self._normalize_output_messages_to_role_parts(
                    span_data
                )
                if normalized_out:
                    payload.output_messages = normalized_out

        elif _is_instance_of(span_data, FunctionSpanData) and capture_tools:

            def _serialize_tool_value(value: Any) -> Optional[str]:
                if value is None:
                    return None
                if isinstance(value, (dict, list)):
                    return safe_json_dumps(value)
                return str(value)

            payload.tool_arguments = _serialize_tool_value(
                getattr(span_data, "input", None)
            )
            payload.tool_result = _serialize_tool_value(
                getattr(span_data, "output", None)
            )

        return payload

    def _find_agent_parent_span_id(
        self, span_id: Optional[str]
    ) -> Optional[str]:
        """Return nearest ancestor span id that represents an agent."""
        current = span_id
        visited: set[str] = set()
        while current:
            if current in visited:
                break
            visited.add(current)
            if current in self._agent_content:
                return current
            current = self._span_parents.get(current)
        return None

    def _update_agent_aggregate(
        self, span: Span[Any], payload: ContentPayload
    ) -> None:
        """Accumulate child span content for parent agent span."""
        agent_id = self._find_agent_parent_span_id(span.parent_id)
        if not agent_id:
            return
        entry = self._agent_content.setdefault(
            agent_id,
            {
                "input_messages": [],
                "output_messages": [],
                "system_instructions": [],
                "request_model": None,
            },
        )
        if payload.input_messages:
            entry["input_messages"] = self._merge_content_sequence(
                entry["input_messages"], payload.input_messages
            )
        if payload.output_messages:
            entry["output_messages"] = self._merge_content_sequence(
                entry["output_messages"], payload.output_messages
            )
        if payload.system_instructions:
            entry["system_instructions"] = self._merge_content_sequence(
                entry["system_instructions"], payload.system_instructions
            )

        if not entry.get("request_model"):
            model = getattr(span.span_data, "model", None)
            if not model:
                response_obj = getattr(span.span_data, "response", None)
                model = getattr(response_obj, "model", None)
            if model:
                entry["request_model"] = model

    def _infer_output_type(self, span_data: Any) -> str:
        """Infer gen_ai.output.type for multiple span kinds."""
        if _is_instance_of(span_data, FunctionSpanData):
            # Tool results are typically JSON
            return GenAIOutputType.JSON
        if _is_instance_of(span_data, TranscriptionSpanData):
            return GenAIOutputType.TEXT
        if _is_instance_of(span_data, SpeechSpanData):
            return GenAIOutputType.SPEECH
        if _is_instance_of(span_data, GuardrailSpanData):
            return GenAIOutputType.TEXT
        if _is_instance_of(span_data, HandoffSpanData):
            return GenAIOutputType.TEXT

        # Check for embeddings operation
        if _is_instance_of(span_data, GenerationSpanData):
            if hasattr(span_data, "embedding_dimension"):
                return (
                    GenAIOutputType.TEXT
                )  # Embeddings are numeric but represented as text

        # Generation/Response - check output structure
        output = getattr(span_data, "output", None) or getattr(
            getattr(span_data, "response", None), "output", None
        )
        if isinstance(output, Sequence) and output:
            first = output[0]
            if isinstance(first, dict):
                item_type = first.get("type")
                if isinstance(item_type, str):
                    normalized = item_type.strip().lower()
                    if normalized in {"image", "image_url"}:
                        return GenAIOutputType.IMAGE
                    if normalized in {"audio", "speech", "audio_url"}:
                        return GenAIOutputType.SPEECH
                    if normalized in {
                        "json",
                        "json_object",
                        "jsonschema",
                        "function_call",
                        "tool_call",
                        "tool_result",
                    }:
                        return GenAIOutputType.JSON
                    if normalized in {
                        "text",
                        "output_text",
                        "message",
                        "assistant",
                    }:
                        return GenAIOutputType.TEXT

                # Conversation style payloads
                if "role" in first:
                    parts = first.get("parts")
                    if isinstance(parts, Sequence) and parts:
                        # If all parts are textual (or missing explicit type), treat as text
                        textual = True
                        for part in parts:
                            if isinstance(part, dict):
                                part_type = str(part.get("type", "")).lower()
                                if part_type in {"image", "image_url"}:
                                    return GenAIOutputType.IMAGE
                                if part_type in {
                                    "audio",
                                    "speech",
                                    "audio_url",
                                }:
                                    return GenAIOutputType.SPEECH
                                if part_type and part_type not in {
                                    "text",
                                    "output_text",
                                    "assistant",
                                }:
                                    textual = False
                            elif not isinstance(part, str):
                                textual = False
                        if textual:
                            return GenAIOutputType.TEXT
                    content_value = first.get("content")
                    if isinstance(content_value, str):
                        return GenAIOutputType.TEXT

                # Detect structured data without explicit type
                json_like_keys = {
                    "schema",
                    "properties",
                    "arguments",
                    "result",
                    "data",
                    "json",
                    "output_json",
                }
                if json_like_keys.intersection(first.keys()):
                    return GenAIOutputType.JSON

        return GenAIOutputType.TEXT

    @staticmethod
    def _sanitize_usage_payload(usage: Any) -> None:
        """Remove non-spec usage fields (e.g., total tokens) in-place."""
        if not usage:
            return
        if isinstance(usage, dict):
            usage.pop("total_tokens", None)
            return
        if hasattr(usage, "total_tokens"):
            try:
                setattr(usage, "total_tokens", None)
            except Exception:  # pragma: no cover - defensive
                try:
                    delattr(usage, "total_tokens")
                except Exception:  # pragma: no cover - defensive
                    pass

    def _get_span_kind(self, span_data: Any) -> SpanKind:
        """Determine appropriate span kind based on span data type."""
        if _is_instance_of(span_data, FunctionSpanData):
            return SpanKind.INTERNAL  # Tool execution is internal
        if _is_instance_of(
            span_data,
            (
                GenerationSpanData,
                ResponseSpanData,
                TranscriptionSpanData,
                SpeechSpanData,
            ),
        ):
            return SpanKind.CLIENT  # API calls to model providers
        if _is_instance_of(span_data, AgentSpanData):
            return SpanKind.CLIENT
        if _is_instance_of(span_data, (GuardrailSpanData, HandoffSpanData)):
            return SpanKind.INTERNAL  # Agent operations are internal
        return SpanKind.INTERNAL

    def on_trace_start(self, trace: Trace) -> None:
        """Create root span when trace starts."""
        if self._tracer:
            attributes = {
                GEN_AI_PROVIDER_NAME: self.system_name,
                GEN_AI_SYSTEM_KEY: self.system_name,
                GEN_AI_OPERATION_NAME: GenAIOperationName.INVOKE_AGENT,
            }
            # Legacy emission removed

            # Add configured agent and server attributes
            if self.agent_name:
                attributes[GEN_AI_AGENT_NAME] = self.agent_name
            if self.agent_id:
                attributes[GEN_AI_AGENT_ID] = self.agent_id
            if self.agent_description:
                attributes[GEN_AI_AGENT_DESCRIPTION] = self.agent_description
            attributes.update(self._get_server_attributes())

            otel_span = self._tracer.start_span(
                name=trace.name,
                attributes=attributes,
                kind=SpanKind.SERVER,  # Root span is typically server
            )
            self._root_spans[trace.trace_id] = otel_span

    def on_trace_end(self, trace: Trace) -> None:
        """End root span when trace ends."""
        if root_span := self._root_spans.pop(trace.trace_id, None):
            if root_span.is_recording():
                root_span.set_status(Status(StatusCode.OK))
            root_span.end()
        self._cleanup_spans_for_trace(trace.trace_id)

    def on_span_start(self, span: Span[Any]) -> None:
        """Start child span for agent span."""
        if not self._tracer or not span.started_at:
            return

        self._span_parents[span.span_id] = span.parent_id
        if (
            _is_instance_of(span.span_data, AgentSpanData)
            and span.span_id not in self._agent_content
        ):
            self._agent_content[span.span_id] = {
                "input_messages": [],
                "output_messages": [],
                "system_instructions": [],
                "request_model": None,
            }

        parent_span = (
            self._otel_spans.get(span.parent_id)
            if span.parent_id
            else self._root_spans.get(span.trace_id)
        )
        context = set_span_in_context(parent_span) if parent_span else None

        # Get operation details for span naming
        operation_name = self._get_operation_name(span.span_data)
        model = getattr(span.span_data, "model", None)
        if model is None:
            response_obj = getattr(span.span_data, "response", None)
            model = getattr(response_obj, "model", None)

        # Use configured agent name or get from span data
        agent_name = self.agent_name
        if not agent_name and _is_instance_of(span.span_data, AgentSpanData):
            agent_name = getattr(span.span_data, "name", None)
        if not agent_name:
            agent_name = self._agent_name_default

        tool_name = (
            getattr(span.span_data, "name", None)
            if _is_instance_of(span.span_data, FunctionSpanData)
            else None
        )

        # Generate spec-compliant span name
        span_name = get_span_name(operation_name, model, agent_name, tool_name)

        attributes = {
            GEN_AI_PROVIDER_NAME: self.system_name,
            GEN_AI_SYSTEM_KEY: self.system_name,
            GEN_AI_OPERATION_NAME: operation_name,
        }
        # Legacy emission removed

        # Add configured agent and server attributes
        agent_name_override = self.agent_name or self._agent_name_default
        agent_id_override = self.agent_id or self._agent_id_default
        agent_desc_override = (
            self.agent_description or self._agent_description_default
        )
        if agent_name_override:
            attributes[GEN_AI_AGENT_NAME] = agent_name_override
        if agent_id_override:
            attributes[GEN_AI_AGENT_ID] = agent_id_override
        if agent_desc_override:
            attributes[GEN_AI_AGENT_DESCRIPTION] = agent_desc_override
        attributes.update(self._get_server_attributes())

        otel_span = self._tracer.start_span(
            name=span_name,
            context=context,
            attributes=attributes,
            kind=self._get_span_kind(span.span_data),
        )
        self._otel_spans[span.span_id] = otel_span
        self._tokens[span.span_id] = attach(set_span_in_context(otel_span))

    def on_span_end(self, span: Span[Any]) -> None:
        """Finalize span with attributes, events, and metrics."""
        if token := self._tokens.pop(span.span_id, None):
            detach(token)

        payload = self._build_content_payload(span)
        self._update_agent_aggregate(span, payload)
        agent_content = (
            self._agent_content.get(span.span_id)
            if _is_instance_of(span.span_data, AgentSpanData)
            else None
        )

        if not (otel_span := self._otel_spans.pop(span.span_id, None)):
            # Log attributes even without OTel span
            try:
                attributes = dict(
                    self._extract_genai_attributes(
                        span, payload, agent_content
                    )
                )
                for key, value in attributes.items():
                    logger.debug(
                        "GenAI attr span %s: %s=%s", span.span_id, key, value
                    )
            except Exception as e:
                logger.warning(
                    "Failed to extract attributes for span %s: %s",
                    span.span_id,
                    e,
                )
            if _is_instance_of(span.span_data, AgentSpanData):
                self._agent_content.pop(span.span_id, None)
            self._span_parents.pop(span.span_id, None)
            return

        try:
            # Extract and set attributes
            attributes: dict[str, AttributeValue] = {}
            # Optimize for non-sampled spans to avoid heavy work
            if not otel_span.is_recording():
                otel_span.end()
                return
            for key, value in self._extract_genai_attributes(
                span, payload, agent_content
            ):
                otel_span.set_attribute(key, value)
                attributes[key] = value

            if _is_instance_of(
                span.span_data, (GenerationSpanData, ResponseSpanData)
            ):
                operation_name = attributes.get(GEN_AI_OPERATION_NAME)
                model_for_name = attributes.get(GEN_AI_REQUEST_MODEL) or (
                    attributes.get(GEN_AI_RESPONSE_MODEL)
                )
                if operation_name and model_for_name:
                    agent_name_for_name = attributes.get(GEN_AI_AGENT_NAME)
                    tool_name_for_name = attributes.get(GEN_AI_TOOL_NAME)
                    new_name = get_span_name(
                        operation_name,
                        model_for_name,
                        agent_name_for_name,
                        tool_name_for_name,
                    )
                    if new_name != otel_span.name:
                        otel_span.update_name(new_name)

            # Emit span events for captured content when configured
            self._emit_content_events(span, otel_span, payload, agent_content)

            # Emit operation details event if configured
            # Set error status if applicable
            otel_span.set_status(status=_get_span_status(span))
            if getattr(span, "error", None):
                err_obj = span.error
                err_type = err_obj.get("type") or err_obj.get("name")
                if err_type:
                    otel_span.set_attribute("error.type", err_type)

            # Record metrics before ending span
            self._record_metrics(span, attributes)

            # End the span
            otel_span.end()

        except Exception as e:
            logger.warning("Failed to enrich span %s: %s", span.span_id, e)
            otel_span.set_status(Status(StatusCode.ERROR, str(e)))
            otel_span.end()
        finally:
            if _is_instance_of(span.span_data, AgentSpanData):
                self._agent_content.pop(span.span_id, None)
            self._span_parents.pop(span.span_id, None)

    def shutdown(self) -> None:
        """Clean up resources on shutdown."""
        for span_id, otel_span in list(self._otel_spans.items()):
            otel_span.set_status(
                Status(StatusCode.ERROR, "Application shutdown")
            )
            otel_span.end()

        for trace_id, root_span in list(self._root_spans.items()):
            root_span.set_status(
                Status(StatusCode.ERROR, "Application shutdown")
            )
            root_span.end()

        self._otel_spans.clear()
        self._root_spans.clear()
        self._tokens.clear()
        self._span_parents.clear()
        self._agent_content.clear()

    def force_flush(self) -> None:
        """Force flush (no-op for this processor)."""
        pass

    def _get_operation_name(self, span_data: Any) -> str:
        """Determine operation name from span data type."""
        if _is_instance_of(span_data, GenerationSpanData):
            # Check if it's embeddings
            if hasattr(span_data, "embedding_dimension"):
                return GenAIOperationName.EMBEDDINGS
            # Check if it's chat or completion
            if span_data.input:
                first_input = span_data.input[0] if span_data.input else None
                if isinstance(first_input, dict) and "role" in first_input:
                    return GenAIOperationName.CHAT
            return GenAIOperationName.TEXT_COMPLETION
        if _is_instance_of(span_data, AgentSpanData):
            # Could be create_agent or invoke_agent based on context
            operation = getattr(span_data, "operation", None)
            normalized = (
                operation.strip().lower()
                if isinstance(operation, str)
                else None
            )
            if normalized in {"create", "create_agent"}:
                return GenAIOperationName.CREATE_AGENT
            if normalized in {"invoke", "invoke_agent"}:
                return GenAIOperationName.INVOKE_AGENT
            return GenAIOperationName.INVOKE_AGENT
        if _is_instance_of(span_data, FunctionSpanData):
            return GenAIOperationName.EXECUTE_TOOL
        if _is_instance_of(span_data, ResponseSpanData):
            return GenAIOperationName.CHAT  # Response typically from chat
        if _is_instance_of(span_data, TranscriptionSpanData):
            return GenAIOperationName.TRANSCRIPTION
        if _is_instance_of(span_data, SpeechSpanData):
            return GenAIOperationName.SPEECH
        if _is_instance_of(span_data, GuardrailSpanData):
            return GenAIOperationName.GUARDRAIL
        if _is_instance_of(span_data, HandoffSpanData):
            return GenAIOperationName.HANDOFF
        return "unknown"

    def _extract_genai_attributes(
        self,
        span: Span[Any],
        payload: ContentPayload,
        agent_content: Optional[Dict[str, list[Any]]] = None,
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Yield (attr, value) pairs for GenAI semantic conventions."""
        span_data = span.span_data

        # Base attributes
        yield GEN_AI_PROVIDER_NAME, self.system_name
        yield GEN_AI_SYSTEM_KEY, self.system_name
        # Legacy emission removed

        # Add configured agent attributes (always include when set)
        agent_name_override = self.agent_name or self._agent_name_default
        agent_id_override = self.agent_id or self._agent_id_default
        agent_desc_override = (
            self.agent_description or self._agent_description_default
        )
        if agent_name_override:
            yield GEN_AI_AGENT_NAME, agent_name_override
        if agent_id_override:
            yield GEN_AI_AGENT_ID, agent_id_override
        if agent_desc_override:
            yield GEN_AI_AGENT_DESCRIPTION, agent_desc_override

        # Server attributes
        for key, value in self._get_server_attributes().items():
            yield key, value

        # Process different span types
        if _is_instance_of(span_data, GenerationSpanData):
            yield from self._get_attributes_from_generation_span_data(
                span_data, payload
            )
        elif _is_instance_of(span_data, AgentSpanData):
            yield from self._get_attributes_from_agent_span_data(
                span_data, agent_content
            )
        elif _is_instance_of(span_data, FunctionSpanData):
            yield from self._get_attributes_from_function_span_data(
                span_data, payload
            )
        elif _is_instance_of(span_data, ResponseSpanData):
            yield from self._get_attributes_from_response_span_data(
                span_data, payload
            )
        elif _is_instance_of(span_data, TranscriptionSpanData):
            yield from self._get_attributes_from_transcription_span_data(
                span_data
            )
        elif _is_instance_of(span_data, SpeechSpanData):
            yield from self._get_attributes_from_speech_span_data(span_data)
        elif _is_instance_of(span_data, GuardrailSpanData):
            yield from self._get_attributes_from_guardrail_span_data(span_data)
        elif _is_instance_of(span_data, HandoffSpanData):
            yield from self._get_attributes_from_handoff_span_data(span_data)

    def _get_attributes_from_generation_span_data(
        self, span_data: GenerationSpanData, payload: ContentPayload
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from generation span."""
        # Operation name
        operation_name = self._get_operation_name(span_data)
        yield GEN_AI_OPERATION_NAME, operation_name

        # Model information
        if span_data.model:
            yield GEN_AI_REQUEST_MODEL, span_data.model

        # Check for embeddings-specific attributes
        if hasattr(span_data, "embedding_dimension"):
            yield (
                GEN_AI_EMBEDDINGS_DIMENSION_COUNT,
                span_data.embedding_dimension,
            )

        # Check for data source
        if hasattr(span_data, "data_source_id"):
            yield GEN_AI_DATA_SOURCE_ID, span_data.data_source_id

        finish_reasons: list[Any] = []
        if span_data.output:
            for part in span_data.output:
                if isinstance(part, dict):
                    fr = part.get("finish_reason") or part.get("stop_reason")
                else:
                    fr = getattr(part, "finish_reason", None)
                if fr:
                    finish_reasons.append(
                        fr if isinstance(fr, str) else str(fr)
                    )
        if finish_reasons:
            yield GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons

        # Usage information
        if span_data.usage:
            usage = span_data.usage
            self._sanitize_usage_payload(usage)
            if "prompt_tokens" in usage or "input_tokens" in usage:
                tokens = usage.get("prompt_tokens") or usage.get(
                    "input_tokens"
                )
                if tokens is not None:
                    yield GEN_AI_USAGE_INPUT_TOKENS, tokens
            if "completion_tokens" in usage or "output_tokens" in usage:
                tokens = usage.get("completion_tokens") or usage.get(
                    "output_tokens"
                )
                if tokens is not None:
                    yield GEN_AI_USAGE_OUTPUT_TOKENS, tokens

        # Model configuration
        if span_data.model_config:
            mc = span_data.model_config
            param_map = {
                "temperature": GEN_AI_REQUEST_TEMPERATURE,
                "top_p": GEN_AI_REQUEST_TOP_P,
                "top_k": GEN_AI_REQUEST_TOP_K,
                "max_tokens": GEN_AI_REQUEST_MAX_TOKENS,
                "presence_penalty": GEN_AI_REQUEST_PRESENCE_PENALTY,
                "frequency_penalty": GEN_AI_REQUEST_FREQUENCY_PENALTY,
                "seed": GEN_AI_REQUEST_SEED,
                "n": GEN_AI_REQUEST_CHOICE_COUNT,
                "stop": GEN_AI_REQUEST_STOP_SEQUENCES,
                "encoding_formats": GEN_AI_REQUEST_ENCODING_FORMATS,
            }
            for k, attr in param_map.items():
                if hasattr(mc, "__contains__") and k in mc:
                    value = mc[k]
                else:
                    value = getattr(mc, k, None)
                if value is not None:
                    yield attr, value

            if hasattr(mc, "get"):
                base_url = (
                    mc.get("base_url")
                    or mc.get("baseUrl")
                    or mc.get("endpoint")
                )
            else:
                base_url = (
                    getattr(mc, "base_url", None)
                    or getattr(mc, "baseUrl", None)
                    or getattr(mc, "endpoint", None)
                )
            for key, value in _infer_server_attributes(base_url).items():
                yield key, value

        # Sensitive data capture
        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_messages
            and payload.input_messages
        ):
            yield (
                GEN_AI_INPUT_MESSAGES,
                safe_json_dumps(payload.input_messages),
            )

        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_system_instructions
            and payload.system_instructions
        ):
            yield (
                GEN_AI_SYSTEM_INSTRUCTIONS,
                safe_json_dumps(payload.system_instructions),
            )

        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_messages
            and payload.output_messages
        ):
            yield (
                GEN_AI_OUTPUT_MESSAGES,
                safe_json_dumps(payload.output_messages),
            )

        # Output type
        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _merge_content_sequence(
        self,
        existing: list[Any],
        incoming: Sequence[Any],
    ) -> list[Any]:
        """Merge normalized message/content lists without duplicating snapshots."""
        if not incoming:
            return existing

        incoming_list = [self._clone_message(item) for item in incoming]

        if self.include_sensitive_data:
            filtered = [
                msg
                for msg in incoming_list
                if not self._is_placeholder_message(msg)
            ]
            if filtered:
                incoming_list = filtered

        if not existing:
            return incoming_list

        result = [self._clone_message(item) for item in existing]

        for idx, new_msg in enumerate(incoming_list):
            if idx < len(result):
                if (
                    self.include_sensitive_data
                    and self._is_placeholder_message(new_msg)
                    and not self._is_placeholder_message(result[idx])
                ):
                    continue
                if result[idx] != new_msg:
                    result[idx] = self._clone_message(new_msg)
            else:
                if (
                    self.include_sensitive_data
                    and self._is_placeholder_message(new_msg)
                ):
                    if (
                        any(
                            not self._is_placeholder_message(existing_msg)
                            for existing_msg in result
                        )
                        or new_msg in result
                    ):
                        continue
                result.append(self._clone_message(new_msg))

        return result

    def _clone_message(self, message: Any) -> Any:
        if isinstance(message, dict):
            return {
                key: self._clone_message(value)
                if isinstance(value, (dict, list))
                else value
                for key, value in message.items()
            }
        if isinstance(message, list):
            return [self._clone_message(item) for item in message]
        return message

    def _is_placeholder_message(self, message: Any) -> bool:
        if not isinstance(message, dict):
            return False
        parts = message.get("parts")
        if not isinstance(parts, list) or not parts:
            return False
        for part in parts:
            if (
                not isinstance(part, dict)
                or part.get("type") != "text"
                or part.get("content") != "readacted"
            ):
                return False
        return True

    def _get_attributes_from_agent_span_data(
        self,
        span_data: AgentSpanData,
        agent_content: Optional[Dict[str, list[Any]]] = None,
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from agent span."""
        yield GEN_AI_OPERATION_NAME, self._get_operation_name(span_data)

        name = (
            self.agent_name
            or getattr(span_data, "name", None)
            or self._agent_name_default
        )
        if name:
            yield GEN_AI_AGENT_NAME, name

        agent_id = (
            self.agent_id
            or getattr(span_data, "agent_id", None)
            or self._agent_id_default
        )
        if agent_id:
            yield GEN_AI_AGENT_ID, agent_id

        description = (
            self.agent_description
            or getattr(span_data, "description", None)
            or self._agent_description_default
        )
        if description:
            yield GEN_AI_AGENT_DESCRIPTION, description

        model = getattr(span_data, "model", None)
        if not model and agent_content:
            model = agent_content.get("request_model")
        if model:
            yield GEN_AI_REQUEST_MODEL, model

        if hasattr(span_data, "conversation_id") and span_data.conversation_id:
            yield GEN_AI_CONVERSATION_ID, span_data.conversation_id

        # Agent definitions
        if self._capture_tool_definitions and hasattr(
            span_data, "agent_definitions"
        ):
            yield (
                GEN_AI_ORCHESTRATOR_AGENT_DEFINITIONS,
                safe_json_dumps(span_data.agent_definitions),
            )

        # System instructions from agent definitions
        if self._capture_system_instructions and hasattr(
            span_data, "agent_definitions"
        ):
            try:
                defs = span_data.agent_definitions
                if isinstance(defs, (list, tuple)):
                    collected: list[dict[str, str]] = []
                    for d in defs:
                        if isinstance(d, dict):
                            msgs = d.get("messages") or d.get(
                                "system_messages"
                            )
                            if isinstance(msgs, (list, tuple)):
                                collected.extend(
                                    self._collect_system_instructions(msgs)
                                )
                    if collected:
                        yield (
                            GEN_AI_SYSTEM_INSTRUCTIONS,
                            safe_json_dumps(collected),
                        )
            except Exception:
                pass

        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_messages
            and agent_content
        ):
            if agent_content.get("input_messages"):
                yield (
                    GEN_AI_INPUT_MESSAGES,
                    safe_json_dumps(agent_content["input_messages"]),
                )
            if agent_content.get("output_messages"):
                yield (
                    GEN_AI_OUTPUT_MESSAGES,
                    safe_json_dumps(agent_content["output_messages"]),
                )
        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_system_instructions
            and agent_content
            and agent_content.get("system_instructions")
        ):
            yield (
                GEN_AI_SYSTEM_INSTRUCTIONS,
                safe_json_dumps(agent_content["system_instructions"]),
            )

        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _get_attributes_from_function_span_data(
        self, span_data: FunctionSpanData, payload: ContentPayload
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from function/tool span."""
        yield GEN_AI_OPERATION_NAME, GenAIOperationName.EXECUTE_TOOL

        if span_data.name:
            yield GEN_AI_TOOL_NAME, span_data.name

        # Tool type - validate and normalize
        tool_type = "function"  # Default for function spans
        if hasattr(span_data, "tool_type"):
            tool_type = span_data.tool_type
        yield GEN_AI_TOOL_TYPE, validate_tool_type(tool_type)

        if hasattr(span_data, "call_id") and span_data.call_id:
            yield GEN_AI_TOOL_CALL_ID, span_data.call_id
        if hasattr(span_data, "description") and span_data.description:
            yield GEN_AI_TOOL_DESCRIPTION, span_data.description

        # Tool definitions
        if self._capture_tool_definitions and hasattr(
            span_data, "tool_definitions"
        ):
            yield (
                GEN_AI_TOOL_DEFINITIONS,
                safe_json_dumps(span_data.tool_definitions),
            )

        # Tool input/output (sensitive)
        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and payload.tool_arguments is not None
        ):
            yield GEN_AI_TOOL_CALL_ARGUMENTS, payload.tool_arguments

        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and payload.tool_result is not None
        ):
            yield GEN_AI_TOOL_CALL_RESULT, payload.tool_result

        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _get_attributes_from_response_span_data(
        self, span_data: ResponseSpanData, payload: ContentPayload
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from response span."""
        yield GEN_AI_OPERATION_NAME, GenAIOperationName.CHAT

        # Response information
        if span_data.response:
            if hasattr(span_data.response, "id") and span_data.response.id:
                yield GEN_AI_RESPONSE_ID, span_data.response.id

            # Model from response
            if (
                hasattr(span_data.response, "model")
                and span_data.response.model
            ):
                yield GEN_AI_RESPONSE_MODEL, span_data.response.model
                if not getattr(span_data, "model", None):
                    yield GEN_AI_REQUEST_MODEL, span_data.response.model

            # Finish reasons
            finish_reasons = []
            if (
                hasattr(span_data.response, "output")
                and span_data.response.output
            ):
                for part in span_data.response.output:
                    if isinstance(part, dict):
                        fr = part.get("finish_reason") or part.get(
                            "stop_reason"
                        )
                    else:
                        fr = getattr(part, "finish_reason", None)
                    if fr:
                        finish_reasons.append(fr)
            if finish_reasons:
                yield GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons

            # Usage from response
            if (
                hasattr(span_data.response, "usage")
                and span_data.response.usage
            ):
                usage = span_data.response.usage
                self._sanitize_usage_payload(usage)
                input_tokens = getattr(usage, "input_tokens", None)
                if input_tokens is None:
                    input_tokens = getattr(usage, "prompt_tokens", None)
                if input_tokens is not None:
                    yield GEN_AI_USAGE_INPUT_TOKENS, input_tokens

                output_tokens = getattr(usage, "output_tokens", None)
                if output_tokens is None:
                    output_tokens = getattr(usage, "completion_tokens", None)
                if output_tokens is not None:
                    yield GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens

        # Input/output messages
        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_messages
            and payload.input_messages
        ):
            yield (
                GEN_AI_INPUT_MESSAGES,
                safe_json_dumps(payload.input_messages),
            )

        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_system_instructions
            and payload.system_instructions
        ):
            yield (
                GEN_AI_SYSTEM_INSTRUCTIONS,
                safe_json_dumps(payload.system_instructions),
            )

        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_messages
            and payload.output_messages
        ):
            yield (
                GEN_AI_OUTPUT_MESSAGES,
                safe_json_dumps(payload.output_messages),
            )

        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _get_attributes_from_transcription_span_data(
        self, span_data: TranscriptionSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from transcription span."""
        yield GEN_AI_OPERATION_NAME, GenAIOperationName.TRANSCRIPTION

        if hasattr(span_data, "model") and span_data.model:
            yield GEN_AI_REQUEST_MODEL, span_data.model

        # Audio format
        if hasattr(span_data, "format") and span_data.format:
            yield "gen_ai.audio.input.format", span_data.format

        # Transcript (sensitive)
        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_messages
            and hasattr(span_data, "transcript")
        ):
            yield "gen_ai.transcription.text", span_data.transcript

        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _get_attributes_from_speech_span_data(
        self, span_data: SpeechSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from speech span."""
        yield GEN_AI_OPERATION_NAME, GenAIOperationName.SPEECH

        if hasattr(span_data, "model") and span_data.model:
            yield GEN_AI_REQUEST_MODEL, span_data.model

        if hasattr(span_data, "voice") and span_data.voice:
            yield "gen_ai.speech.voice", span_data.voice

        if hasattr(span_data, "format") and span_data.format:
            yield "gen_ai.audio.output.format", span_data.format

        # Input text (sensitive)
        if (
            self.include_sensitive_data
            and self._content_mode.capture_in_span
            and self._capture_messages
            and hasattr(span_data, "input_text")
        ):
            yield "gen_ai.speech.input_text", span_data.input_text

        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _get_attributes_from_guardrail_span_data(
        self, span_data: GuardrailSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from guardrail span."""
        yield GEN_AI_OPERATION_NAME, GenAIOperationName.GUARDRAIL

        if span_data.name:
            yield GEN_AI_GUARDRAIL_NAME, span_data.name

        yield GEN_AI_GUARDRAIL_TRIGGERED, span_data.triggered
        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _get_attributes_from_handoff_span_data(
        self, span_data: HandoffSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from handoff span."""
        yield GEN_AI_OPERATION_NAME, GenAIOperationName.HANDOFF

        if span_data.from_agent:
            yield GEN_AI_HANDOFF_FROM_AGENT, span_data.from_agent

        if span_data.to_agent:
            yield GEN_AI_HANDOFF_TO_AGENT, span_data.to_agent

        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _cleanup_spans_for_trace(self, trace_id: str) -> None:
        """Clean up spans for a trace to prevent memory leaks."""
        spans_to_remove = [
            span_id
            for span_id in self._otel_spans.keys()
            if span_id.startswith(trace_id)
        ]
        for span_id in spans_to_remove:
            if otel_span := self._otel_spans.pop(span_id, None):
                otel_span.set_status(
                    Status(
                        StatusCode.ERROR, "Trace ended before span completion"
                    )
                )
                otel_span.end()
            self._tokens.pop(span_id, None)


__all__ = [
    "GenAIProvider",
    "GenAIOperationName",
    "GenAIToolType",
    "GenAIOutputType",
    "GenAIEvaluationAttributes",
    "ContentCaptureMode",
    "ContentPayload",
    "GenAISemanticProcessor",
    "normalize_provider",
    "normalize_output_type",
    "validate_tool_type",
]
