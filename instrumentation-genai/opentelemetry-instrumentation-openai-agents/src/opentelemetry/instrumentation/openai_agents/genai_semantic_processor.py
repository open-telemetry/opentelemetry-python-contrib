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
from urllib.parse import urlparse
from typing import TYPE_CHECKING, Any, Iterator, Optional, Sequence

from opentelemetry._events import Event
from opentelemetry.context import attach, detach
from opentelemetry.trace import Span as OtelSpan
from opentelemetry.trace import (
    Status,
    StatusCode,
    Tracer,
    set_span_in_context,
)
from opentelemetry.util.types import AttributeValue
from agents.tracing import Span, Trace, TracingProcessor
from agents.tracing.span_data import (
    AgentSpanData,
    FunctionSpanData,
    GenerationSpanData,
    GuardrailSpanData,
    HandoffSpanData,
    ResponseSpanData,
    TranscriptionSpanData,
    SpeechSpanData,
)
from openai.types.responses import (
    ResponseOutputMessage,
    ResponseFunctionToolCall,
)

# Metrics/content gating utilities
from .utils import is_metrics_enabled, is_content_enabled
from . import instruments

if TYPE_CHECKING:
    from typing_extensions import assert_never

"""Attribute constant notes.

Includes both spec-compliant names and (deprecated) legacy names. The
processor emits spec attributes; legacy ones retained temporarily for
backward compatibility. Remove legacy attributes after deprecation.
"""

# ---- Spec attributes ----
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
GEN_AI_ORCHESTRATOR_AGENT_DEFINITIONS = "gen_ai.orchestrator.agent_definitions"
GEN_AI_DATA_SOURCE_ID = "gen_ai.data_source.id"
GEN_AI_OUTPUT_TYPE = "gen_ai.output.type"
GEN_AI_SYSTEM_INSTRUCTIONS = "gen_ai.system_instructions"
GEN_AI_INPUT_MESSAGES = "gen_ai.input.messages"
GEN_AI_OUTPUT_MESSAGES = "gen_ai.output.messages"
GEN_AI_GUARDRAIL_NAME = "gen_ai.guardrail.name"
GEN_AI_GUARDRAIL_TRIGGERED = "gen_ai.guardrail.triggered"
GEN_AI_HANDOFF_FROM_AGENT = "gen_ai.handoff.from_agent"
GEN_AI_HANDOFF_TO_AGENT = "gen_ai.handoff.to_agent"

# ---- Legacy (deprecated) attribute names (keep temporarily) ----
GEN_AI_SYSTEM_LEGACY = "gen_ai.system"  # -> gen_ai.provider.name
GEN_AI_PROMPT_LEGACY = "gen_ai.prompt"  # -> gen_ai.input.messages
GEN_AI_COMPLETION_LEGACY = "gen_ai.completion"  # -> gen_ai.output.messages
GEN_AI_TOOL_INPUT_LEGACY = "gen_ai.tool.input"  # -> gen_ai.tool.call.arguments
GEN_AI_TOOL_OUTPUT_LEGACY = "gen_ai.tool.output"  # -> gen_ai.tool.call.result

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
    except Exception:  # pragma: no cover - defensive
        return {}
    return out


def _get_function_span_event(span: Span[Any], otel_span: OtelSpan) -> Event:
    """
    Create an OpenTelemetry event for a function span.
    
    Args:
        span: The span to create the event for
        otel_span: The OpenTelemetry span context
    
    Returns:
        An OpenTelemetry Event with function call details
    """
    span_data = span.span_data
    if not isinstance(span_data, FunctionSpanData):
        assert_never(span_data)  # Ensure type safety
    
    input_event = Event(
        name="gen_ai.assistant.message",
        attributes={"gen_ai.system": "openai"},
        body={
            "role": "assistant",
            "tool_calls": [
                {
                    # 'id': span_data.call_id,
                    "type": "function",
                    "function": {
                        "name": span_data.name,
                        "arguments": span_data.input,
                    },
                }
            ],
        },
        span_id=otel_span.context.span_id if otel_span else None,
        trace_id=otel_span.context.trace_id if otel_span else None,
    )

    output_event = Event(
        name="gen_ai.tool.message",
        attributes={"gen_ai.system": "openai"},
        body={
            "content": span_data.output,
            # 'id': span_data.call_id,
            "role": "function",
        },
        span_id=otel_span.context.span_id if otel_span else None,
        trace_id=otel_span.context.trace_id if otel_span else None,
    )

    return [input_event, output_event]


def _get_response_span_event(span, otel_span):
    span_data = span.span_data
    input_messages = (
        span_data.input if isinstance(span_data, ResponseSpanData) else None
    )
    output_parts = (
        span_data.response.output
        if isinstance(span_data, ResponseSpanData)
        else None
    )

    input_events = []
    output_events = []

    for message in input_messages:
        # Default to "message" if type is not specified
        message_type = message.get("type", "message")
        if message_type == "message":
            input_events.append(
                Event(
                    name=f'gen_ai.{message_type}.message',
                    attributes={
                        "gen_ai.system": "openai",
                    },
                    body=message,
                    span_id=otel_span.context.span_id if otel_span else None,
                    trace_id=otel_span.context.trace_id if otel_span else None,
                )
            )
        
        elif message_type == "function_call_output":
            input_events.append(
                Event(
                    name="gen_ai.tool.message",
                    attributes={
                        "gen_ai.system": "openai",
                    },
                    body={
                        'role': 'tool',
                        'content': message.get("output", ""),  # type: ignore
                    },
                    span_id=(
                        otel_span.context.span_id if otel_span else None
                    ),  # type: ignore
                    trace_id=(
                        otel_span.context.trace_id if otel_span else None
                    ),  # type: ignore
                )
            )
        elif message_type == "function_call":
            input_events.append(  # type: ignore
                Event(
                    name="gen_ai.assistant.message",
                    attributes={
                        "gen_ai.system": "openai",
                    },
                    body={
                        'role': 'assistant',
                        'tool_calls': [
                            {
                                'id': message.get("call_id"),  # type: ignore
                                'type': 'function',
                                'function': {
                                    'name': message.get("name"),
                                    'arguments': message.get("arguments"),
                                }
                            }
                        ]
                    },
                    span_id=(
                        otel_span.context.span_id if otel_span else None
                    ),  # type: ignore
                    trace_id=(
                        otel_span.context.trace_id if otel_span else None
                    ),
                )
            )

    for output_message in output_parts:
        if isinstance(output_message, ResponseOutputMessage):
            output_events.append(  # type: ignore
                Event(
                    name="gen_ai.choice",
                    attributes={"gen_ai.system": "openai"},
                    body={
                        "role": output_message.role,
                        "message": {
                            "content": span_data.response.output_text[:500]
                            if getattr(span_data.response, "output_text", None)
                            else "",  # type: ignore
                        },
                    },
                    span_id=(
                        otel_span.context.span_id if otel_span else None
                    ),  # type: ignore
                    trace_id=(
                        otel_span.context.trace_id if otel_span else None
                    ),  # type: ignore
                )
            )

        if isinstance(output_message, ResponseFunctionToolCall):
            output_events.append(  # type: ignore
                Event(
                    name="gen_ai.assistant.message",
                    attributes={"gen_ai.system": "openai"},
                    body={
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": output_message.call_id,
                                "type": "function",
                                "function": {
                                    "name": output_message.name,
                                    "arguments": output_message.arguments,
                                },
                            }
                        ],
                    },
                    span_id=(
                        otel_span.context.span_id if otel_span else None
                    ),  # type: ignore
                    trace_id=(
                        otel_span.context.trace_id if otel_span else None
                    ),  # type: ignore
                )
            )

    return input_events + output_events  # type: ignore


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


class GenAISemanticProcessor(TracingProcessor):
    """Trace processor adding GenAI semantic convention attributes.

    Uses iterator-based extraction (OpenInference style) to populate
    standardized attributes across span types.
    """

    def __init__(
        self,
        tracer: Optional[Tracer] = None,
        event_logger: Optional[Any] = None,
        system_name: str = "openai",
        include_sensitive_data: bool = True,
        base_url: Optional[str] = None,
        emit_legacy: bool = True,
    ):
        """Init processor (OpenInference style helper).

        tracer: optional OTel tracer
        event_logger: optional event sink
        system_name: provider name (openai/azure.ai.inference/etc.)
        include_sensitive_data: include model/tool IO when True
        base_url: API endpoint (for server.address/port)
        emit_legacy: also emit deprecated attribute names
        """
        self._tracer = tracer
        self._event_logger = event_logger
    # system_name historically mapped to provider -> provider.name
        self.system_name = system_name
        self.include_sensitive_data = include_sensitive_data
        self.base_url = base_url
        self.emit_legacy = emit_legacy

        # Track spans and contexts following OpenInference pattern
        self._root_spans: dict[str, OtelSpan] = {}
        self._otel_spans: dict[str, OtelSpan] = {}
        self._tokens: dict[str, object] = {}
        self._metrics_enabled = is_metrics_enabled()
        # cache instruments lazily when first needed
        self._metric_instruments = None

    # ---------------- Internal helpers (system instructions, output type) ----------------
    def _collect_system_instructions(self, messages: Sequence[Any] | None) -> list[str]:
        """Return list of system/ai role message contents.

        Messages can be list[dict] where each dict has role/content.
        """
        if not messages:
            return []
        out: list[str] = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            if role in {"system", "ai"}:
                content = m.get("content")
                if content is not None:
                    out.append(str(content))
        return out

    def _infer_output_type(self, span_data: Any) -> str:
        """Infer gen_ai.output.type for multiple span kinds.

        Heuristics:
          - Function/tool span: tool_result
          - Transcription: audio_transcript
          - Speech: audio_speech
          - Guardrail: guardrail_check
          - Handoff: agent_handoff
          - Generation/Response: if output has dict items with 'type' use first; else 'text'
        """
        if isinstance(span_data, FunctionSpanData):
            return "tool_result"
        if isinstance(span_data, TranscriptionSpanData):
            return "audio_transcript"
        if isinstance(span_data, SpeechSpanData):
            return "audio_speech"
        if isinstance(span_data, GuardrailSpanData):
            return "guardrail_check"
        if isinstance(span_data, HandoffSpanData):
            return "agent_handoff"
        # Generation / Response style
        output = getattr(span_data, "output", None) or getattr(getattr(span_data, "response", None), "output", None)
        if isinstance(output, Sequence) and output:
            first = output[0]
            if isinstance(first, dict):
                t = first.get("type") or first.get("role")
                if t:
                    return str(t)
        return "text"

    def on_trace_start(self, trace: Trace) -> None:
        """Create root span when trace starts (if tracer present)."""
        if self._tracer:
            attributes = {
                GEN_AI_PROVIDER_NAME: self.system_name,
            }
            if self.emit_legacy:
                attributes[GEN_AI_SYSTEM_LEGACY] = self.system_name
            attributes.update(_infer_server_attributes(self.base_url))
            otel_span = self._tracer.start_span(
                name=trace.name, attributes=attributes
            )
            self._root_spans[trace.trace_id] = otel_span

    def on_trace_end(self, trace: Trace) -> None:
        """Called when a trace is finished. End root span if exists."""
        if root_span := self._root_spans.pop(trace.trace_id, None):
            root_span.set_status(Status(StatusCode.OK))
            root_span.end()
        
        # Clean up any remaining spans for this trace
        self._cleanup_spans_for_trace(trace.trace_id)

    def on_span_start(self, span: Span[Any]) -> None:
        """Start child span for agent span (if tracer)."""
        if not self._tracer or not span.started_at:
            return
            
        # start_time = datetime.fromisoformat(span.started_at)
        parent_span = (
            self._otel_spans.get(span.parent_id)
            if span.parent_id
            else self._root_spans.get(span.trace_id)
        )
        context = set_span_in_context(parent_span) if parent_span else None
        
        attributes = {
            GEN_AI_PROVIDER_NAME: self.system_name,
        }
        if self.emit_legacy:
            attributes[GEN_AI_SYSTEM_LEGACY] = self.system_name
        attributes.update(_infer_server_attributes(self.base_url))
        otel_span = self._tracer.start_span(
            name=self._get_span_name(span),
            context=context,
            attributes=attributes,
        )
        self._otel_spans[span.span_id] = otel_span
        self._tokens[span.span_id] = attach(set_span_in_context(otel_span))

    def on_span_end(self, span: Span[Any]) -> None:
        """Finalize span, enrich with semantic attributes, end span."""
        # Detach context token if exists
        if token := self._tokens.pop(span.span_id, None):
            detach(token)  # type: ignore[arg-type]
            
        # Get the OpenTelemetry span if it exists
        if not (otel_span := self._otel_spans.pop(span.span_id, None)):
            # If no OTel span, just log attributes (debug)
            try:
                attributes = dict(self._extract_genai_attributes(span))
                
                # Log to event logger if available
                if self._event_logger:
                    self._log_event_to_logger(
                        span, attributes, otel_span
                    )  # type: ignore
                
                # Also log for debugging
                for key, value in attributes.items():
                    logger.debug(
                        "GenAI attr span %s: %s=%s", span.span_id, key, value
                    )
            except Exception as e:
                logger.warning(
                    "Failed to enrich span %s: %s", span.span_id, e
                )
            return
            
        try:
            # Set attributes and collect for event logging
            attributes: dict[str, AttributeValue] = {}
            for key, value in self._extract_genai_attributes(span):
                otel_span.set_attribute(key, value)
                attributes[key] = value
                
            # Log to event logger if available
            if self._event_logger:
                self._log_event_to_logger(span, attributes, otel_span)
                
            # Calculate end time if available
            if span.ended_at:
                # Placeholder: could convert to nanoseconds if needed
                pass
                    
            # Set span status and end the span
            otel_span.set_status(status=_get_span_status(span))
            # Emit error.type if applicable
            if getattr(span, "error", None):
                err_obj = span.error  # type: ignore[attr-defined]
                err_type = err_obj.get("type") or err_obj.get("name")
                if err_type:
                    otel_span.set_attribute("error.type", err_type)
            otel_span.end()

            # Metrics (post-end to ensure attributes captured). We only record for core model/tool spans.
            if self._metrics_enabled:
                from datetime import datetime as _dt
                try:
                    if self._metric_instruments is None:
                        self._metric_instruments = instruments.get_instruments()
                    sd = span.span_data
                    # Only record for model-centric or tool spans
                    if isinstance(sd, (GenerationSpanData, ResponseSpanData, FunctionSpanData, AgentSpanData)):
                        end_dt = None
                        start_dt = None
                        if getattr(span, "started_at", None):
                            try:
                                start_dt = _dt.fromisoformat(span.started_at)  # type: ignore[arg-type]
                            except Exception:
                                pass
                        if getattr(span, "ended_at", None):
                            try:
                                end_dt = _dt.fromisoformat(span.ended_at)  # type: ignore[arg-type]
                            except Exception:
                                pass
                        duration_s = None
                        if start_dt and end_dt:
                            duration_s = (end_dt - start_dt).total_seconds()
                        # Build common metric attributes
                        metric_attrs = {
                            "gen_ai.operation.name": attributes.get(GEN_AI_OPERATION_NAME),
                            "gen_ai.request.model": attributes.get(GEN_AI_REQUEST_MODEL) or attributes.get(GEN_AI_RESPONSE_MODEL),
                            "gen_ai.provider.name": self.system_name,
                        }
                        # Drop None values
                        metric_attrs = {k: v for k, v in metric_attrs.items() if v is not None}
                        instruments.record_request(**metric_attrs)
                        if duration_s is not None:
                            instruments.record_duration(duration_s, **metric_attrs)
                        # Token metrics if present
                        in_toks = attributes.get(GEN_AI_USAGE_INPUT_TOKENS)
                        out_toks = attributes.get(GEN_AI_USAGE_OUTPUT_TOKENS)
                        try:
                            instruments.record_tokens(in_toks if isinstance(in_toks, (int, float)) else None, out_toks if isinstance(out_toks, (int, float)) else None, **metric_attrs)
                        except Exception:
                            pass
                except Exception as m_exc:  # pragma: no cover - defensive
                    logger.debug("Metric emission failed: %s", m_exc)
            
        except Exception as e:
            logger.warning(
                "Failed to enrich span %s: %s", span.span_id, e
            )
            otel_span.set_status(Status(StatusCode.ERROR, str(e)))
            otel_span.end()

    def shutdown(self) -> None:
        """Called when the application stops. Clean up resources."""
        # End any remaining spans
        for span_id, otel_span in list(self._otel_spans.items()):
            otel_span.set_status(
                Status(StatusCode.ERROR, "Application shutdown")
            )
            otel_span.end()
        
        # End any remaining root spans
        for trace_id, root_span in list(self._root_spans.items()):
            root_span.set_status(
                Status(StatusCode.ERROR, "Application shutdown")
            )
            root_span.end()
            
        # Clear all tracking dictionaries
        self._otel_spans.clear()
        self._root_spans.clear()
        self._tokens.clear()

    def force_flush(self) -> None:
        """Force any pending operations (no-op)."""
        pass

    def _extract_genai_attributes(
        self, span: Span[Any]
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Yield (attr, value) pairs for GenAI semantic conventions."""
        span_data = span.span_data
        
        # Base attributes common to all GenAI operations
        yield GEN_AI_PROVIDER_NAME, self.system_name
        if self.emit_legacy:
            yield GEN_AI_SYSTEM_LEGACY, self.system_name
        
        # Process different span types using the OpenInference pattern
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
        """Extract attributes from a generation span using iterator pattern."""
        
        # Determine operation type; default chat if messages are structured
        op_name = "chat"
        if span_data.input:
            first_input = span_data.input[0]
            if not (isinstance(first_input, dict) and 'role' in first_input):
                op_name = "text_completion"
        yield GEN_AI_OPERATION_NAME, op_name
        
        # Model information
        if span_data.model:
            yield GEN_AI_REQUEST_MODEL, span_data.model
        
        # Usage information
        if span_data.usage:
            usage = span_data.usage
            for key_map in (
                ("prompt_tokens", GEN_AI_USAGE_INPUT_TOKENS),
                ("input_tokens", GEN_AI_USAGE_INPUT_TOKENS),
                ("completion_tokens", GEN_AI_USAGE_OUTPUT_TOKENS),
                ("output_tokens", GEN_AI_USAGE_OUTPUT_TOKENS),
                ("total_tokens", GEN_AI_USAGE_TOTAL_TOKENS),
            ):  # iterate and emit first present per alias
                key, attr = key_map
                if key in usage:
                    yield attr, usage[key]
        
        # Model configuration parameters
        if span_data.model_config:
            mc = span_data.model_config
            # direct params
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
        
        # Input/output data (if sensitive data is allowed)
        if self.include_sensitive_data and is_content_enabled():
            if span_data.input:
                yield GEN_AI_INPUT_MESSAGES, safe_json_dumps(span_data.input)
                if self.emit_legacy:
                    yield GEN_AI_PROMPT_LEGACY, safe_json_dumps(span_data.input)
                # system instructions from inputs
                sys_instr = self._collect_system_instructions(span_data.input)
                if sys_instr:
                    yield GEN_AI_SYSTEM_INSTRUCTIONS, safe_json_dumps(sys_instr)
            if span_data.output:
                yield GEN_AI_OUTPUT_MESSAGES, safe_json_dumps(span_data.output)
                if self.emit_legacy:
                    yield GEN_AI_COMPLETION_LEGACY, safe_json_dumps(span_data.output)
        # Always attempt output type inference
        yield GEN_AI_OUTPUT_TYPE, self._infer_output_type(span_data)

    def _get_attributes_from_agent_span_data(
        self, span_data: AgentSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from an agent span using iterator pattern."""
        
        yield GEN_AI_OPERATION_NAME, "invoke_agent"
        if span_data.name:
            yield GEN_AI_AGENT_NAME, span_data.name
        if getattr(span_data, "agent_id", None):
            yield GEN_AI_AGENT_ID, span_data.agent_id  # type: ignore[attr-defined]
        if getattr(span_data, "description", None):
            yield GEN_AI_AGENT_DESCRIPTION, span_data.description  # type: ignore[attr-defined]
        if getattr(span_data, "conversation_id", None):
            yield GEN_AI_CONVERSATION_ID, span_data.conversation_id  # type: ignore[attr-defined]
        if getattr(span_data, "agent_definitions", None):
            yield GEN_AI_ORCHESTRATOR_AGENT_DEFINITIONS, safe_json_dumps(span_data.agent_definitions)  # type: ignore[attr-defined]
            # system instructions from nested agent definitions (if any messages)
            try:
                defs = span_data.agent_definitions  # type: ignore[attr-defined]
                if isinstance(defs, (list, tuple)):
                    collected: list[str] = []
                    for d in defs:
                        msgs = None
                        if isinstance(d, dict):
                            msgs = d.get("messages") or d.get("system_messages")
                        if isinstance(msgs, (list, tuple)):
                            collected.extend(self._collect_system_instructions(msgs))
                    if collected:
                        yield GEN_AI_SYSTEM_INSTRUCTIONS, safe_json_dumps(collected)
            except Exception:
                pass
        # Output type for agent spans (aggregate)
        yield GEN_AI_OUTPUT_TYPE, self._infer_output_type(span_data)

    def _get_attributes_from_function_span_data(
        self, span_data: FunctionSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from a function span using iterator pattern."""
        
        yield GEN_AI_OPERATION_NAME, "execute_tool"
        if span_data.name:
            yield GEN_AI_TOOL_NAME, span_data.name
        yield GEN_AI_TOOL_TYPE, "function"
        if getattr(span_data, "call_id", None):
            yield GEN_AI_TOOL_CALL_ID, span_data.call_id  # type: ignore[attr-defined]
        if getattr(span_data, "description", None):
            yield GEN_AI_TOOL_DESCRIPTION, span_data.description  # type: ignore[attr-defined]
        if getattr(span_data, "tool_definitions", None):
            yield GEN_AI_TOOL_DEFINITIONS, safe_json_dumps(span_data.tool_definitions)  # type: ignore[attr-defined]
        if self.include_sensitive_data:
            if span_data.input is not None:
                arg_val = safe_json_dumps(span_data.input) if isinstance(span_data.input, (dict, list)) else str(span_data.input)
                yield GEN_AI_TOOL_CALL_ARGUMENTS, arg_val
                if self.emit_legacy:
                    yield GEN_AI_TOOL_INPUT_LEGACY, arg_val
            if span_data.output is not None:
                res_val = safe_json_dumps(span_data.output) if isinstance(span_data.output, (dict, list)) else str(span_data.output)
                yield GEN_AI_TOOL_CALL_RESULT, res_val
                if self.emit_legacy:
                    yield GEN_AI_TOOL_OUTPUT_LEGACY, res_val
        yield GEN_AI_OUTPUT_TYPE, self._infer_output_type(span_data)

    def _get_attributes_from_response_span_data(
        self, span_data: ResponseSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from a response span using iterator pattern."""
        yield GEN_AI_OPERATION_NAME, "response"
        
        # Response information
        if span_data.response:
            if hasattr(span_data.response, 'id') and span_data.response.id:
                yield GEN_AI_RESPONSE_ID, span_data.response.id
            
            # Model information from response
            if hasattr(span_data.response, 'model') and span_data.response.model:
                yield GEN_AI_RESPONSE_MODEL, span_data.response.model
                # Some APIs echo request.model only in response; ensure request model present if missing
                if not getattr(span_data, 'model', None):
                    yield GEN_AI_REQUEST_MODEL, span_data.response.model
            # finish reasons
            finish_reasons = []
            if hasattr(span_data.response, 'output') and span_data.response.output:
                for part in span_data.response.output:
                    fr = getattr(part, 'finish_reason', None)
                    if fr:
                        finish_reasons.append(fr)
            if finish_reasons:
                yield GEN_AI_RESPONSE_FINISH_REASONS, finish_reasons
            
            # Usage information from response
            if hasattr(span_data.response, 'usage') and span_data.response.usage:
                usage = span_data.response.usage
                if hasattr(usage, 'prompt_tokens') and usage.prompt_tokens is not None:
                    yield GEN_AI_USAGE_INPUT_TOKENS, usage.prompt_tokens
                if hasattr(usage, 'completion_tokens') and usage.completion_tokens is not None:
                    yield GEN_AI_USAGE_OUTPUT_TOKENS, usage.completion_tokens
                if hasattr(usage, 'total_tokens') and usage.total_tokens is not None:
                    yield GEN_AI_USAGE_TOTAL_TOKENS, usage.total_tokens
        
        # Input data (if sensitive data is allowed)
        if self.include_sensitive_data and is_content_enabled() and span_data.input:
            if isinstance(span_data.input, (list, tuple)):
                yield GEN_AI_INPUT_MESSAGES, safe_json_dumps(span_data.input)
                if self.emit_legacy:
                    yield GEN_AI_PROMPT_LEGACY, safe_json_dumps(span_data.input)
                sys_instr = self._collect_system_instructions(span_data.input)
                if sys_instr:
                    yield GEN_AI_SYSTEM_INSTRUCTIONS, safe_json_dumps(sys_instr)
            else:
                yield GEN_AI_INPUT_MESSAGES, safe_json_dumps(span_data.input)
        # Output messages if available (content enabled)
        output_messages = getattr(getattr(span_data, "response", None), "output", None)
        if self.include_sensitive_data and is_content_enabled() and output_messages:
            # Collect ResponseOutputMessage textual content if present
            collected = []
            for part in output_messages:
                if isinstance(part, ResponseOutputMessage):
                    content = getattr(getattr(span_data, "response", None), "output_text", None)
                    if content:
                        collected.append(content)
            if collected:
                yield GEN_AI_OUTPUT_MESSAGES, safe_json_dumps(collected)
                if self.emit_legacy:
                    yield GEN_AI_COMPLETION_LEGACY, safe_json_dumps(collected)
        # Output type inference
        yield GEN_AI_OUTPUT_TYPE, self._infer_output_type(span_data)

    def _get_attributes_from_transcription_span_data(
        self, span_data: TranscriptionSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from a transcription span using iterator pattern."""
        yield GEN_AI_OPERATION_NAME, "transcription"
        
        # Model information for transcription
        if hasattr(span_data, 'model') and span_data.model:
            yield GEN_AI_REQUEST_MODEL, span_data.model
        
        # Audio input information (without sensitive data)
        if hasattr(span_data, 'format') and span_data.format:
            yield "gen_ai.audio.input.format", span_data.format
        
        # Transcription output (if sensitive data is allowed)
        if self.include_sensitive_data and is_content_enabled() and hasattr(span_data, 'transcript') and span_data.transcript:
            yield "gen_ai.transcription.text", span_data.transcript
        yield GEN_AI_OUTPUT_TYPE, self._infer_output_type(span_data)

    def _get_attributes_from_speech_span_data(
        self, span_data: SpeechSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from a speech span using iterator pattern."""
        yield GEN_AI_OPERATION_NAME, "speech_generation"
        
        # Model information for speech synthesis
        if hasattr(span_data, 'model') and span_data.model:
            yield GEN_AI_REQUEST_MODEL, span_data.model
        
        # Voice information
        if hasattr(span_data, 'voice') and span_data.voice:
            yield "gen_ai.speech.voice", span_data.voice
        
        # Audio output format
        if hasattr(span_data, 'format') and span_data.format:
            yield "gen_ai.audio.output.format", span_data.format
        
        # Input text (if sensitive data is allowed)
        if self.include_sensitive_data and is_content_enabled() and hasattr(span_data, 'input_text') and span_data.input_text:
            yield "gen_ai.speech.input_text", span_data.input_text
        yield GEN_AI_OUTPUT_TYPE, self._infer_output_type(span_data)

    def _get_attributes_from_guardrail_span_data(
        self, span_data: GuardrailSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from a guardrail span using iterator pattern."""
        yield GEN_AI_OPERATION_NAME, "guardrail_check"
        
        # Add guardrail-specific information
        if span_data.name:
            yield GEN_AI_GUARDRAIL_NAME, span_data.name
        
        yield GEN_AI_GUARDRAIL_TRIGGERED, span_data.triggered
        yield GEN_AI_OUTPUT_TYPE, self._infer_output_type(span_data)

    def _get_attributes_from_handoff_span_data(
        self, span_data: HandoffSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from a handoff span using iterator pattern."""
        yield GEN_AI_OPERATION_NAME, "agent_handoff"
        
        # Add handoff information
        if span_data.from_agent:
            yield GEN_AI_HANDOFF_FROM_AGENT, span_data.from_agent
        
        if span_data.to_agent:
            yield GEN_AI_HANDOFF_TO_AGENT, span_data.to_agent
        yield GEN_AI_OUTPUT_TYPE, self._infer_output_type(span_data)

    def _get_span_name(self, span: Span[Any]) -> str:
        """Get a descriptive name for the span following OpenInference pattern."""
        if hasattr(data := span.span_data, "name") and isinstance(name := data.name, str):
            if isinstance(span.span_data, AgentSpanData) and name:
                return f'invoke_agent {name}'
            return name
        if isinstance(span.span_data, HandoffSpanData) and span.span_data.to_agent:
            return f"handoff to {span.span_data.to_agent}"
        return type(span.span_data).__name__.replace("SpanData", "").lower()

    def _cleanup_spans_for_trace(self, trace_id: str) -> None:
        """Clean up any remaining spans for a trace to prevent memory leaks."""
        spans_to_remove = [span_id for span_id in self._otel_spans.keys() if span_id.startswith(trace_id)]
        for span_id in spans_to_remove:
            if otel_span := self._otel_spans.pop(span_id, None):
                otel_span.set_status(Status(StatusCode.ERROR, "Trace ended before span completion"))
                otel_span.end()
            self._tokens.pop(span_id, None)

    def _log_event_to_logger(self, span: Span[Any], attributes: dict[str, AttributeValue], otel_span) -> None:
        """Log GenAI event using the event logger if available."""
        if not self._event_logger:
            return
        
        try:
            events = None
            if isinstance(span.span_data, ResponseSpanData):
                events = _get_response_span_event(span, otel_span)
                
            if isinstance(span.span_data, FunctionSpanData):
                events = _get_function_span_event(span, otel_span)

            if events:
                for event in events:
                        self._event_logger.emit(event)

        except Exception as e:
            logger.warning(f"Failed to log GenAI event for span {span.span_id}: {e}")