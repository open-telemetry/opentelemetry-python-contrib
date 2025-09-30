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

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterator, Optional, Sequence
from urllib.parse import urlparse

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
from openai.types.responses import (
    ResponseOutputMessage,
)

from opentelemetry.context import attach, detach
from opentelemetry.metrics import Histogram, get_meter
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
from .constants import (
    GEN_AI_AGENT_DESCRIPTION,
    GEN_AI_AGENT_ID,
    GEN_AI_AGENT_NAME,
    GEN_AI_CONVERSATION_ID,
    GEN_AI_DATA_SOURCE_ID,
    GEN_AI_EMBEDDINGS_DIMENSION_COUNT,
    GEN_AI_GUARDRAIL_NAME,
    GEN_AI_GUARDRAIL_TRIGGERED,
    GEN_AI_HANDOFF_FROM_AGENT,
    GEN_AI_HANDOFF_TO_AGENT,
    GEN_AI_INPUT_MESSAGES,
    GEN_AI_OPERATION_NAME,
    GEN_AI_ORCHESTRATOR_AGENT_DEFINITIONS,
    GEN_AI_OUTPUT_MESSAGES,
    GEN_AI_OUTPUT_TYPE,
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_CHOICE_COUNT,
    GEN_AI_REQUEST_ENCODING_FORMATS,
    GEN_AI_REQUEST_FREQUENCY_PENALTY,
    GEN_AI_REQUEST_MAX_TOKENS,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_REQUEST_PRESENCE_PENALTY,
    GEN_AI_REQUEST_SEED,
    GEN_AI_REQUEST_STOP_SEQUENCES,
    GEN_AI_REQUEST_TEMPERATURE,
    GEN_AI_REQUEST_TOP_K,
    GEN_AI_REQUEST_TOP_P,
    GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_RESPONSE_ID,
    GEN_AI_RESPONSE_MODEL,
    GEN_AI_SYSTEM_INSTRUCTIONS,
    GEN_AI_TOOL_CALL_ARGUMENTS,
    GEN_AI_TOOL_CALL_ID,
    GEN_AI_TOOL_CALL_RESULT,
    GEN_AI_TOOL_DEFINITIONS,
    GEN_AI_TOOL_DESCRIPTION,
    GEN_AI_TOOL_NAME,
    GEN_AI_TOOL_TYPE,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    GEN_AI_USAGE_TOTAL_TOKENS,
    GenAIOperationName,
    GenAIOutputType,
)
from .events import emit_operation_details_event

# Import utilities and event helpers
from .utils import (
    normalize_output_type,
    normalize_provider,
    validate_tool_type,
)

if TYPE_CHECKING:
    pass

# Legacy attributes removed

logger = logging.getLogger(__name__)


def _infer_server_attributes(base_url: Optional[str]) -> dict[str, Any]:
    """Return server.address / server.port attributes if base_url provided."""
    out: dict[str, Any] = {}
    if not base_url:
        return out
    try:
        parsed = urlparse(base_url)
        if parsed.hostname:
            out["server.address"] = parsed.hostname
        if parsed.port:
            out["server.port"] = parsed.port
    except Exception:
        return {}
    return out


def safe_json_dumps(obj: Any) -> str:
    """Safely convert object to JSON string (fallback to str)."""
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(obj)


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
    if operation_name == GenAIOperationName.CHAT:
        return f"chat {model}" if model else "chat"
    elif operation_name == GenAIOperationName.TEXT_COMPLETION:
        return f"text_completion {model}" if model else "text_completion"
    elif operation_name == GenAIOperationName.EMBEDDINGS:
        return f"embeddings {model}" if model else "embeddings"
    elif operation_name == GenAIOperationName.CREATE_AGENT:
        return f"create_agent {agent_name}" if agent_name else "create_agent"
    elif operation_name == GenAIOperationName.INVOKE_AGENT:
        return f"invoke_agent {agent_name}" if agent_name else "invoke_agent"
    elif operation_name == GenAIOperationName.EXECUTE_TOOL:
        return f"execute_tool {tool_name}" if tool_name else "execute_tool"
    elif operation_name == GenAIOperationName.TRANSCRIPTION:
        return f"transcription {model}" if model else "transcription"
    elif operation_name == GenAIOperationName.SPEECH:
        return f"speech {model}" if model else "speech"
    elif operation_name == GenAIOperationName.GUARDRAIL:
        return "guardrail"
    elif operation_name == GenAIOperationName.HANDOFF:
        return f"handoff {agent_name}" if agent_name else "handoff"
    return operation_name


class GenAISemanticProcessor(TracingProcessor):
    """Trace processor adding GenAI semantic convention attributes with metrics."""

    def __init__(
        self,
        tracer: Optional[Tracer] = None,
        event_logger: Optional[Any] = None,
        system_name: str = "openai",
        include_sensitive_data: bool = True,
        base_url: Optional[str] = None,
        emit_legacy: bool = True,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_description: Optional[str] = None,
        server_address: Optional[str] = None,
        server_port: Optional[int] = None,
    ):
        """Initialize processor with metrics support.

        Args:
            tracer: Optional OpenTelemetry tracer
            event_logger: Optional event logger for detailed events
            system_name: Provider name (openai/azure.ai.inference/etc.)
            include_sensitive_data: Include model/tool IO when True
            base_url: API endpoint for server.address/port
            emit_legacy: Also emit deprecated attribute names
            agent_name: Name of the agent (can be overridden by env var)
            agent_id: ID of the agent (can be overridden by env var)
            agent_description: Description of the agent (can be overridden by env var)
            server_address: Server address (can be overridden by env var or base_url)
            server_port: Server port (can be overridden by env var or base_url)
        """
        self._tracer = tracer
        self._event_logger = event_logger
        self.system_name = normalize_provider(system_name) or system_name
        self.include_sensitive_data = include_sensitive_data
        self.base_url = base_url
        # Legacy emission removed; parameter retained for compatibility but unused
        self.emit_legacy = False

        # Agent information - use init parameters or defaults
        self.agent_name = agent_name or "agent"
        self.agent_id = agent_id or "unknown"
        self.agent_description = agent_description or "instrumented agent"

        # Server information - use init parameters, then base_url inference
        self.server_address = server_address
        self.server_port = server_port

        # If server info not provided, try to extract from base_url
        if (not self.server_address or not self.server_port) and base_url:
            server_attrs = _infer_server_attributes(base_url)
            if not self.server_address:
                self.server_address = server_attrs.get("server.address")
            if not self.server_port:
                self.server_port = server_attrs.get("server.port")

        # Span tracking
        self._root_spans: dict[str, OtelSpan] = {}
        self._otel_spans: dict[str, OtelSpan] = {}
        self._tokens: dict[str, object] = {}

        # Metrics configuration (always enabled)
        self._metrics_enabled = True
        self._meter = None
        self._duration_histogram: Optional[Histogram] = None
        self._token_usage_histogram: Optional[Histogram] = None

        # Configuration for attribute capture (always enabled)
        self._capture_system_instructions = True
        self._capture_messages = True
        self._capture_tool_definitions = True

        # Initialize metrics if enabled
        if self._metrics_enabled:
            self._init_metrics()

    def _get_server_attributes(self) -> dict[str, Any]:
        """Get server attributes from configured values."""
        attrs = {}
        if self.server_address:
            attrs["server.address"] = self.server_address
        if self.server_port:
            attrs["server.port"] = self.server_port
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
        if not self._metrics_enabled or not self._duration_histogram:
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
                "gen_ai.provider.name": attributes.get(GEN_AI_PROVIDER_NAME),
                "gen_ai.operation.name": attributes.get(GEN_AI_OPERATION_NAME),
                "gen_ai.request.model": (
                    attributes.get(GEN_AI_REQUEST_MODEL)
                    or attributes.get(GEN_AI_RESPONSE_MODEL)
                ),
                "server.address": attributes.get("server.address"),
                "server.port": attributes.get("server.port"),
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
            if duration is not None:
                self._duration_histogram.record(duration, metric_attrs)

            # Record token usage
            if self._token_usage_histogram:
                input_tokens = attributes.get(GEN_AI_USAGE_INPUT_TOKENS)
                if isinstance(input_tokens, (int, float)):
                    token_attrs = dict(metric_attrs)
                    token_attrs["gen_ai.token.type"] = "input"
                    self._token_usage_histogram.record(
                        input_tokens, token_attrs
                    )

                output_tokens = attributes.get(GEN_AI_USAGE_OUTPUT_TOKENS)
                if isinstance(output_tokens, (int, float)):
                    token_attrs = dict(metric_attrs)
                    token_attrs["gen_ai.token.type"] = "output"
                    self._token_usage_histogram.record(
                        output_tokens, token_attrs
                    )

        except Exception as e:
            logger.debug("Failed to record metrics: %s", e)

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

            normalized.append(
                {"role": role, "parts": parts or self._redacted_text_parts()}
            )

        return normalized

    def _infer_output_type(self, span_data: Any) -> str:
        """Infer gen_ai.output.type for multiple span kinds."""
        if isinstance(span_data, FunctionSpanData):
            # Tool results are typically JSON
            return GenAIOutputType.JSON
        if isinstance(span_data, TranscriptionSpanData):
            return GenAIOutputType.TEXT
        if isinstance(span_data, SpeechSpanData):
            return GenAIOutputType.SPEECH
        if isinstance(span_data, GuardrailSpanData):
            return GenAIOutputType.TEXT
        if isinstance(span_data, HandoffSpanData):
            return GenAIOutputType.TEXT

        # Check for embeddings operation
        if isinstance(span_data, GenerationSpanData):
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
                # Check for image/speech indicators
                if first.get("type") == "image":
                    return GenAIOutputType.IMAGE
                if first.get("type") == "audio":
                    return GenAIOutputType.SPEECH
                # Check if it's structured JSON
                if "type" in first or len(first) > 1:
                    return GenAIOutputType.JSON

        return GenAIOutputType.TEXT

    def _get_span_kind(self, span_data: Any) -> SpanKind:
        """Determine appropriate span kind based on span data type."""
        if isinstance(span_data, FunctionSpanData):
            return SpanKind.INTERNAL  # Tool execution is internal
        if isinstance(
            span_data,
            (
                GenerationSpanData,
                ResponseSpanData,
                TranscriptionSpanData,
                SpeechSpanData,
            ),
        ):
            return SpanKind.CLIENT  # API calls to model providers
        if isinstance(
            span_data, (AgentSpanData, GuardrailSpanData, HandoffSpanData)
        ):
            return SpanKind.INTERNAL  # Agent operations are internal
        return SpanKind.INTERNAL

    def on_trace_start(self, trace: Trace) -> None:
        """Create root span when trace starts."""
        if self._tracer:
            attributes = {
                GEN_AI_PROVIDER_NAME: self.system_name,
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

        parent_span = (
            self._otel_spans.get(span.parent_id)
            if span.parent_id
            else self._root_spans.get(span.trace_id)
        )
        context = set_span_in_context(parent_span) if parent_span else None

        # Get operation details for span naming
        operation_name = self._get_operation_name(span.span_data)
        model = getattr(span.span_data, "model", None)

        # Use configured agent name or get from span data
        agent_name = self.agent_name
        if not agent_name and isinstance(span.span_data, AgentSpanData):
            agent_name = getattr(span.span_data, "name", None)

        tool_name = (
            getattr(span.span_data, "name", None)
            if isinstance(span.span_data, FunctionSpanData)
            else None
        )

        # Generate spec-compliant span name
        span_name = get_span_name(operation_name, model, agent_name, tool_name)

        attributes = {
            GEN_AI_PROVIDER_NAME: self.system_name,
            GEN_AI_OPERATION_NAME: operation_name,
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

        if not (otel_span := self._otel_spans.pop(span.span_id, None)):
            # Log attributes even without OTel span
            try:
                attributes = dict(self._extract_genai_attributes(span))
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
            return

        try:
            # Extract and set attributes
            attributes: dict[str, AttributeValue] = {}
            # Optimize for non-sampled spans to avoid heavy work
            if not otel_span.is_recording():
                otel_span.end()
                return
            for key, value in self._extract_genai_attributes(span):
                otel_span.set_attribute(key, value)
                attributes[key] = value

            # Emit operation details event if configured
            if self._event_logger:
                emit_operation_details_event(
                    self._event_logger, attributes, otel_span
                )

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

    def force_flush(self) -> None:
        """Force flush (no-op for this processor)."""
        pass

    def _get_operation_name(self, span_data: Any) -> str:
        """Determine operation name from span data type."""
        if isinstance(span_data, GenerationSpanData):
            # Check if it's embeddings
            if hasattr(span_data, "embedding_dimension"):
                return GenAIOperationName.EMBEDDINGS
            # Check if it's chat or completion
            if span_data.input:
                first_input = span_data.input[0] if span_data.input else None
                if isinstance(first_input, dict) and "role" in first_input:
                    return GenAIOperationName.CHAT
            return GenAIOperationName.TEXT_COMPLETION
        elif isinstance(span_data, AgentSpanData):
            # Could be create_agent or invoke_agent based on context
            # Default to invoke_agent (more common)
            return GenAIOperationName.INVOKE_AGENT
        elif isinstance(span_data, FunctionSpanData):
            return GenAIOperationName.EXECUTE_TOOL
        elif isinstance(span_data, ResponseSpanData):
            return GenAIOperationName.CHAT  # Response typically from chat
        elif isinstance(span_data, TranscriptionSpanData):
            return GenAIOperationName.TRANSCRIPTION
        elif isinstance(span_data, SpeechSpanData):
            return GenAIOperationName.SPEECH
        elif isinstance(span_data, GuardrailSpanData):
            return GenAIOperationName.GUARDRAIL
        elif isinstance(span_data, HandoffSpanData):
            return GenAIOperationName.HANDOFF
        return "unknown"

    def _extract_genai_attributes(
        self, span: Span[Any]
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Yield (attr, value) pairs for GenAI semantic conventions."""
        span_data = span.span_data

        # Base attributes
        yield GEN_AI_PROVIDER_NAME, self.system_name
        # Legacy emission removed

        # Add configured agent attributes (always include when set)
        if self.agent_name:
            yield GEN_AI_AGENT_NAME, self.agent_name
        if self.agent_id:
            yield GEN_AI_AGENT_ID, self.agent_id
        if self.agent_description:
            yield GEN_AI_AGENT_DESCRIPTION, self.agent_description

        # Server attributes
        for key, value in self._get_server_attributes().items():
            yield key, value

        # Process different span types
        if isinstance(span_data, GenerationSpanData):
            yield from self._get_attributes_from_generation_span_data(
                span_data
            )
        elif isinstance(span_data, AgentSpanData):
            yield from self._get_attributes_from_agent_span_data(span_data)
        elif isinstance(span_data, FunctionSpanData):
            yield from self._get_attributes_from_function_span_data(span_data)
        elif isinstance(span_data, ResponseSpanData):
            yield from self._get_attributes_from_response_span_data(span_data)
        elif isinstance(span_data, TranscriptionSpanData):
            yield from self._get_attributes_from_transcription_span_data(
                span_data
            )
        elif isinstance(span_data, SpeechSpanData):
            yield from self._get_attributes_from_speech_span_data(span_data)
        elif isinstance(span_data, GuardrailSpanData):
            yield from self._get_attributes_from_guardrail_span_data(span_data)
        elif isinstance(span_data, HandoffSpanData):
            yield from self._get_attributes_from_handoff_span_data(span_data)

    def _get_attributes_from_generation_span_data(
        self, span_data: GenerationSpanData
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

        # Usage information
        if span_data.usage:
            usage = span_data.usage
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
            if "total_tokens" in usage:
                yield GEN_AI_USAGE_TOTAL_TOKENS, usage["total_tokens"]

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
                if k in mc and mc[k] is not None:
                    yield attr, mc[k]

        # Sensitive data capture
        if self.include_sensitive_data:
            # Input messages (normalized to role+parts)
            if self._capture_messages and span_data.input:
                normalized_in = self._normalize_messages_to_role_parts(
                    span_data.input
                )
                yield GEN_AI_INPUT_MESSAGES, safe_json_dumps(normalized_in)

            # System instructions
            if self._capture_system_instructions and span_data.input:
                if self.include_sensitive_data:
                    sys_instr = self._collect_system_instructions(
                        span_data.input
                    )
                else:
                    sys_instr = self._redacted_text_parts()
                if sys_instr:
                    yield (
                        GEN_AI_SYSTEM_INSTRUCTIONS,
                        safe_json_dumps(sys_instr),
                    )

            # Output messages (leave as-is; not normalized here)
            if self._capture_messages and span_data.output:
                yield GEN_AI_OUTPUT_MESSAGES, safe_json_dumps(span_data.output)

        # Output type
        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _get_attributes_from_agent_span_data(
        self, span_data: AgentSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from agent span."""
        yield GEN_AI_OPERATION_NAME, GenAIOperationName.INVOKE_AGENT

        # Use span data values only if not configured globally
        if not self.agent_name and span_data.name:
            yield GEN_AI_AGENT_NAME, span_data.name
        if (
            not self.agent_id
            and hasattr(span_data, "agent_id")
            and span_data.agent_id
        ):
            yield GEN_AI_AGENT_ID, span_data.agent_id
        if (
            not self.agent_description
            and hasattr(span_data, "description")
            and span_data.description
        ):
            yield GEN_AI_AGENT_DESCRIPTION, span_data.description
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

        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _get_attributes_from_function_span_data(
        self, span_data: FunctionSpanData
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
        if self.include_sensitive_data:
            if span_data.input is not None:
                arg_val = (
                    safe_json_dumps(span_data.input)
                    if isinstance(span_data.input, (dict, list))
                    else str(span_data.input)
                )
                yield GEN_AI_TOOL_CALL_ARGUMENTS, arg_val
                # Legacy emission removed

            if span_data.output is not None:
                res_val = (
                    safe_json_dumps(span_data.output)
                    if isinstance(span_data.output, (dict, list))
                    else str(span_data.output)
                )
                yield GEN_AI_TOOL_CALL_RESULT, res_val
                # Legacy emission removed

        yield (
            GEN_AI_OUTPUT_TYPE,
            normalize_output_type(self._infer_output_type(span_data)),
        )

    def _get_attributes_from_response_span_data(
        self, span_data: ResponseSpanData
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
                if (
                    hasattr(usage, "prompt_tokens")
                    and usage.prompt_tokens is not None
                ):
                    yield GEN_AI_USAGE_INPUT_TOKENS, usage.prompt_tokens
                if (
                    hasattr(usage, "completion_tokens")
                    and usage.completion_tokens is not None
                ):
                    yield GEN_AI_USAGE_OUTPUT_TOKENS, usage.completion_tokens
                if (
                    hasattr(usage, "total_tokens")
                    and usage.total_tokens is not None
                ):
                    yield GEN_AI_USAGE_TOTAL_TOKENS, usage.total_tokens

        # Input/output messages
        if self.include_sensitive_data:
            # Input messages (normalized to role+parts)
            if self._capture_messages and span_data.input:
                normalized_in = self._normalize_messages_to_role_parts(
                    span_data.input
                )
                yield GEN_AI_INPUT_MESSAGES, safe_json_dumps(normalized_in)

            # System instructions
            if self._capture_system_instructions and span_data.input:
                if self.include_sensitive_data:
                    sys_instr = self._collect_system_instructions(
                        span_data.input
                    )
                else:
                    sys_instr = self._redacted_text_parts()
                if sys_instr:
                    yield (
                        GEN_AI_SYSTEM_INSTRUCTIONS,
                        safe_json_dumps(sys_instr),
                    )

            # Output messages (leave as-is; not normalized here)
            if self._capture_messages:
                output_messages = getattr(
                    getattr(span_data, "response", None), "output", None
                )
                if output_messages:
                    collected = []
                    for part in output_messages:
                        if isinstance(part, ResponseOutputMessage):
                            content = getattr(
                                getattr(span_data, "response", None),
                                "output_text",
                                None,
                            )
                            if content:
                                collected.append(content)
                    if collected:
                        yield (
                            GEN_AI_OUTPUT_MESSAGES,
                            safe_json_dumps(collected),
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
        if self.include_sensitive_data:
            if self._capture_messages and hasattr(span_data, "transcript"):
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
        if self.include_sensitive_data:
            if self._capture_messages and hasattr(span_data, "input_text"):
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
