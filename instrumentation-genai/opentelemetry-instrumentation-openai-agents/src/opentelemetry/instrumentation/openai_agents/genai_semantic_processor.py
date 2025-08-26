"""
GenAI Semantic Convention Trace Processor

This module implements a custom trace processor that enriches spans with OpenTelemetry GenAI 
semantic conventions attributes following the OpenInference processor pattern. It adds 
standardized attributes for generative AI operations using iterator-based attribute extraction.

References:
- OpenTelemetry GenAI Semantic Conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/
- OpenInference Pattern: https://github.com/Arize-ai/openinference
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterator, Optional

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
from openai.types.responses import ResponseOutputMessage, ResponseFunctionToolCall

if TYPE_CHECKING:
    from typing_extensions import assert_never

# GenAI Semantic Convention Constants
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_REQUEST_TOP_P = "gen_ai.request.top_p" 
GEN_AI_REQUEST_TOP_K = "gen_ai.request.top_k"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_REQUEST_PRESENCE_PENALTY = "gen_ai.request.presence_penalty"
GEN_AI_REQUEST_FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"
GEN_AI_PROMPT = "gen_ai.prompt"
GEN_AI_COMPLETION = "gen_ai.completion"
GEN_AI_RESPONSE_ID = "gen_ai.response.id"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_INPUT = "gen_ai.tool.input" 
GEN_AI_TOOL_OUTPUT = "gen_ai.tool.output"
GEN_AI_HANDOFF_FROM_AGENT = "gen_ai.handoff.from_agent"
GEN_AI_HANDOFF_TO_AGENT = "gen_ai.handoff.to_agent"
GEN_AI_GUARDRAIL_NAME = "gen_ai.guardrail.name"
GEN_AI_GUARDRAIL_TRIGGERED = "gen_ai.guardrail.triggered"

logger = logging.getLogger(__name__)

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
        name='gen_ai.assistant.message',
        attributes={
            "gen_ai.system": "openai",
        },
        body={
                'role': 'assistant',
                'tool_calls': [
                    {
                        # 'id': span_data.call_id,
                        'type': 'function',
                            'function': {
                                'name': span_data.name,
                                'arguments': span_data.input,
                            }
                        }
                    ]
                },
        span_id=otel_span.context.span_id if otel_span else None,
        trace_id=otel_span.context.trace_id if otel_span else None,
    )

    output_event =  Event(
        name='gen_ai.tool.message',
        attributes={
            "gen_ai.system": "openai",
        },
        body={
            'content': span_data.output,
            # 'id': span_data.call_id,
            'role': 'function',
        },
        span_id=otel_span.context.span_id if otel_span else None,
        trace_id=otel_span.context.trace_id if otel_span else None,
    )

    return [input_event, output_event]

def _get_response_span_event(span, otel_span):
    span_data = span.span_data
    input = span_data.input if isinstance(span_data, ResponseSpanData) else None
    output = span_data.response.output if isinstance(span_data, ResponseSpanData) else None

    input_events = []
    output_events = []

    for message in input:
        message_type = message.get("type", "message") # Default to "message" if type is not specified
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
                    name=f'gen_ai.tool.message',
                    attributes={
                        "gen_ai.system": "openai",
                    },
                    body={
                        'role': 'tool',
                        'content': message.get("output", ""), # type: ignore
                    },
                    span_id=otel_span.context.span_id if otel_span else None, # type: ignore
                    trace_id=otel_span.context.trace_id if otel_span else None, # type: ignore
                )
            )
        elif message_type == "function_call":
            input_events.append( # type: ignore
                Event(
                    name=f'gen_ai.assistant.message',
                    attributes={
                        "gen_ai.system": "openai",
                    },
                    body={
                        'role': 'assistant',
                        'tool_calls': [
                            {
                                'id': message.get("call_id"), # type: ignore
                                'type': 'function',
                                'function': {
                                    'name': message.get("name"),
                                    'arguments': message.get("arguments"),
                                }
                            }
                        ]
                    },
                    span_id=otel_span.context.span_id if otel_span else None, # type: ignore
                    trace_id=otel_span.context.trace_id if otel_span else None,
                )
            )

    for output_message in output:
        if isinstance(output_message, ResponseOutputMessage):
                output_events.append( # type: ignore
                    Event(
                        name='gen_ai.choice',
                        attributes={
                            "gen_ai.system": "openai",
                        },
                        body={
                            'role': output_message.role,
                            'message': {
                                'content': span_data.response.output_text # type: ignore
                            }
                        },
                        span_id=otel_span.context.span_id if otel_span else None, # type: ignore
                        trace_id=otel_span.context.trace_id if otel_span else None, # type: ignore
                    )
                )

        if isinstance(output_message, ResponseFunctionToolCall):
            output_events.append( # type: ignore
                Event(
                    name=f'gen_ai.assistant.message',
                    attributes={
                        "gen_ai.system": "openai",
                    },
                    body={
                        'role': 'assistant',
                        'tool_calls': [
                            {
                                'id': output_message.call_id,
                                'type': 'function',
                                'function': {
                                    'name': output_message.name,
                                    'arguments': output_message.arguments,
                                }
                            }
                        ]
                    },
                    span_id=otel_span.context.span_id if otel_span else None, # type: ignore
                    trace_id=otel_span.context.trace_id if otel_span else None, # type: ignore
                )
            )
            
    
    return input_events + output_events # type: ignore

def safe_json_dumps(obj: Any) -> str:
    """Safely convert an object to JSON string, following OpenInference pattern."""
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
            description=f"{error.get('message', '')}: {error.get('data', '')}"
        )
    return Status(StatusCode.OK)


class GenAISemanticProcessor(TracingProcessor):
    """
    A trace processor that enriches spans with OpenTelemetry GenAI semantic convention attributes.
    
    This processor follows the OpenInference pattern using iterator-based attribute extraction
    to add standardized attributes to spans for generative AI operations. It processes different 
    span types and adds appropriate GenAI attributes based on the span's operation type.
    
    Supported span types:
    - GenerationSpanData: LLM model calls (gen_ai.operation.name = "chat" or "text_completion")
    - AgentSpanData: Agent operations (gen_ai.operation.name = "invoke_agent")
    - FunctionSpanData: Tool execution (gen_ai.operation.name = "execute_tool")
    - ResponseSpanData: Response tracking (gen_ai.operation.name = "response")
    - TranscriptionSpanData: Speech-to-text (gen_ai.operation.name = "transcription")
    - SpeechSpanData: Text-to-speech (gen_ai.operation.name = "speech_generation")
    - GuardrailSpanData: Safety/validation operations (gen_ai.operation.name = "guardrail_check")
    - HandoffSpanData: Agent handoff operations (gen_ai.operation.name = "agent_handoff")
    """

    def __init__(self, tracer: Optional[Tracer] = None, event_logger: Optional[Any] = None, 
                 system_name: str = "openai", include_sensitive_data: bool = True):
        """
        Initialize the GenAI semantic processor following OpenInference pattern.
        
        Args:
            tracer: OpenTelemetry tracer for creating spans (optional)
            event_logger: Event logger for logging GenAI events (optional)
            system_name: The GenAI system identifier (default: "openai")
            include_sensitive_data: Whether to include input/output data in attributes
        """
        self._tracer = tracer
        self._event_logger = event_logger
        self.system_name = system_name
        self.include_sensitive_data = include_sensitive_data
        
        # Track spans and contexts following OpenInference pattern
        self._root_spans: dict[str, OtelSpan] = {}
        self._otel_spans: dict[str, OtelSpan] = {}
        self._tokens: dict[str, object] = {}

    def on_trace_start(self, trace: Trace) -> None:
        """Called when a trace is started. Create root OpenTelemetry span if tracer available."""
        if self._tracer:
            otel_span = self._tracer.start_span(
                name=trace.name,
                attributes={
                    GEN_AI_SYSTEM: self.system_name,
                },
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
        """Called when a span is started. Create OpenTelemetry span if tracer available."""
        if not self._tracer or not span.started_at:
            return
            
        # start_time = datetime.fromisoformat(span.started_at)
        parent_span = (
            self._otel_spans.get(span.parent_id)
            if span.parent_id
            else self._root_spans.get(span.trace_id)
        )
        context = set_span_in_context(parent_span) if parent_span else None
        
        otel_span = self._tracer.start_span(
            name=self._get_span_name(span),
            context=context,
            # start_time=_as_utc_nano(start_time),
            # start_time=span.started_at,
            attributes={
                GEN_AI_SYSTEM: self.system_name,
            },
        )
        self._otel_spans[span.span_id] = otel_span
        self._tokens[span.span_id] = attach(set_span_in_context(otel_span))

    def on_span_end(self, span: Span[Any]) -> None:
        """
        Called when a span is finished. Enriches the span with GenAI semantic convention attributes.
        
        Args:
            span: The finished span to enrich with GenAI attributes
        """
        # Detach context token if exists
        if token := self._tokens.pop(span.span_id, None):
            detach(token)  # type: ignore[arg-type]
            
        # Get the OpenTelemetry span if it exists
        if not (otel_span := self._otel_spans.pop(span.span_id, None)):
            # If no OpenTelemetry span, just log the attributes for demonstration
            try:
                attributes = dict(self._extract_genai_attributes(span))
                
                # Log to event logger if available
                if self._event_logger:
                    self._log_event_to_logger(span, attributes, otel_span) # type: ignore
                
                # Also log for debugging
                for key, value in attributes.items():
                    logger.debug(f"Setting GenAI attribute on span {span.span_id}: {key} = {value}")
            except Exception as e:
                logger.warning(f"Failed to enrich span {span.span_id} with GenAI attributes: {e}")
            return
            
        try:
            # Set attributes on the OpenTelemetry span and collect them for event logging
            attributes = {}
            for key, value in self._extract_genai_attributes(span):
                otel_span.set_attribute(key, value)
                attributes[key] = value
                
            # Log to event logger if available
            if self._event_logger:
                self._log_event_to_logger(span, attributes, otel_span)
                
            # Calculate end time if available
            end_time: Optional[int] = None
            if span.ended_at:
                try:
                    # end_time = _as_utc_nano(datetime.fromisoformat(span.ended_at))
                    end_time = span.ended_at
                except ValueError:
                    pass
                    
            # Set span status and end the span
            otel_span.set_status(status=_get_span_status(span))
            # otel_span.end(end_time)
            otel_span.end()
            
        except Exception as e:
            logger.warning(f"Failed to enrich span {span.span_id} with GenAI attributes: {e}")
            otel_span.set_status(Status(StatusCode.ERROR, str(e)))
            otel_span.end()

    def shutdown(self) -> None:
        """Called when the application stops. Clean up resources."""
        # End any remaining spans
        for span_id, otel_span in list(self._otel_spans.items()):
            otel_span.set_status(Status(StatusCode.ERROR, "Application shutdown"))
            otel_span.end()
        
        # End any remaining root spans
        for trace_id, root_span in list(self._root_spans.items()):
            root_span.set_status(Status(StatusCode.ERROR, "Application shutdown"))
            root_span.end()
            
        # Clear all tracking dictionaries
        self._otel_spans.clear()
        self._root_spans.clear() 
        self._tokens.clear()

    def force_flush(self) -> None:
        """Force any pending operations to complete. No-op for this processor."""
        pass

    def _extract_genai_attributes(self, span: Span[Any]) -> Iterator[tuple[str, AttributeValue]]:
        """
        Extract GenAI semantic convention attributes from a span using iterator pattern.
        
        Args:
            span: The span to extract attributes from
            
        Yields:
            Tuples of (attribute_key, attribute_value) for GenAI semantic conventions
        """
        span_data = span.span_data
        
        # Base attributes common to all GenAI operations
        yield GEN_AI_SYSTEM, self.system_name
        
        # Process different span types using the OpenInference pattern
        if isinstance(span_data, GenerationSpanData):
            yield from self._get_attributes_from_generation_span_data(span_data)
        elif isinstance(span_data, AgentSpanData):
            yield from self._get_attributes_from_agent_span_data(span_data)
        elif isinstance(span_data, FunctionSpanData):
            yield from self._get_attributes_from_function_span_data(span_data)
        elif isinstance(span_data, ResponseSpanData):
            yield from self._get_attributes_from_response_span_data(span_data)
        elif isinstance(span_data, TranscriptionSpanData):
            yield from self._get_attributes_from_transcription_span_data(span_data)
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
        
        # Determine operation type based on the input/output format
        if span_data.input and len(span_data.input) > 0:
            # Check if it's a chat completion (messages) or text completion
            first_input = span_data.input[0] if span_data.input else {}
            if isinstance(first_input, dict) and 'role' in first_input:
                yield GEN_AI_OPERATION_NAME, "chat"
            else:
                yield GEN_AI_OPERATION_NAME, "text_completion"
        else:
            yield GEN_AI_OPERATION_NAME, "chat"  # Default to chat
        
        # Model information
        if span_data.model:
            yield GEN_AI_REQUEST_MODEL, span_data.model
        
        # Usage information
        if span_data.usage:
            if "prompt_tokens" in span_data.usage:
                yield GEN_AI_USAGE_INPUT_TOKENS, span_data.usage["prompt_tokens"]
            elif "input_tokens" in span_data.usage:
                yield GEN_AI_USAGE_INPUT_TOKENS, span_data.usage["input_tokens"]
                
            if "completion_tokens" in span_data.usage:
                yield GEN_AI_USAGE_OUTPUT_TOKENS, span_data.usage["completion_tokens"]
            elif "output_tokens" in span_data.usage:
                yield GEN_AI_USAGE_OUTPUT_TOKENS, span_data.usage["output_tokens"]
                
            if "total_tokens" in span_data.usage:
                yield GEN_AI_USAGE_TOTAL_TOKENS, span_data.usage["total_tokens"]
        
        # Model configuration parameters
        if span_data.model_config:
            for param, value in span_data.model_config.items():
                if param in ["temperature", "top_p", "top_k", "max_tokens", "presence_penalty", "frequency_penalty"]:
                    yield f"gen_ai.request.{param}", value
        
        # Input/output data (if sensitive data is allowed)
        if self.include_sensitive_data:
            if span_data.input:
                yield GEN_AI_PROMPT, safe_json_dumps(span_data.input)
            if span_data.output:
                yield GEN_AI_COMPLETION, safe_json_dumps(span_data.output)

    def _get_attributes_from_agent_span_data(
        self, span_data: AgentSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from an agent span using iterator pattern."""
        
        yield GEN_AI_OPERATION_NAME, "invoke_agent"
        
        # Agent information
        if span_data.name:
            yield GEN_AI_AGENT_NAME, span_data.name

    def _get_attributes_from_function_span_data(
        self, span_data: FunctionSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from a function span using iterator pattern."""
        
        yield GEN_AI_OPERATION_NAME, "execute_tool"
        
        # Function/tool information
        if span_data.name:
            yield GEN_AI_TOOL_NAME, span_data.name
            
        # Input/output data (if sensitive data is allowed)
        if self.include_sensitive_data:
            if span_data.input is not None:
                if isinstance(span_data.input, (dict, list)):
                    yield GEN_AI_TOOL_INPUT, safe_json_dumps(span_data.input)
                else:
                    yield GEN_AI_TOOL_INPUT, str(span_data.input)
            
            if span_data.output is not None:
                if isinstance(span_data.output, (dict, list)):
                    yield GEN_AI_TOOL_OUTPUT, safe_json_dumps(span_data.output)
                else:
                    yield GEN_AI_TOOL_OUTPUT, str(span_data.output)

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
                yield GEN_AI_REQUEST_MODEL, span_data.response.model
            
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
        if self.include_sensitive_data and span_data.input:
            if isinstance(span_data.input, (dict, list)):
                yield "gen_ai.response.input", safe_json_dumps(span_data.input)
            else:
                yield "gen_ai.response.input", str(span_data.input)

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
        if self.include_sensitive_data and hasattr(span_data, 'transcript') and span_data.transcript:
            yield "gen_ai.transcription.text", span_data.transcript

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
        if self.include_sensitive_data and hasattr(span_data, 'input_text') and span_data.input_text:
            yield "gen_ai.speech.input_text", span_data.input_text

    def _get_attributes_from_guardrail_span_data(
        self, span_data: GuardrailSpanData
    ) -> Iterator[tuple[str, AttributeValue]]:
        """Extract attributes from a guardrail span using iterator pattern."""
        
        yield GEN_AI_OPERATION_NAME, "guardrail_check"
        
        # Add guardrail-specific information
        if span_data.name:
            yield GEN_AI_GUARDRAIL_NAME, span_data.name
        
        yield GEN_AI_GUARDRAIL_TRIGGERED, span_data.triggered

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