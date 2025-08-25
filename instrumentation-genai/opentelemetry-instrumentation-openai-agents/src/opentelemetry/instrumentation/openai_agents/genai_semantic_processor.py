"""GenAI semantic processor for OpenAI Agents SDK traces.

Provides attribute, event, and metric mapping from OpenAI Agents internal
tracing objects to OpenTelemetry GenAI semantic conventions (draft).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional, Iterable

from .utils import (
    is_content_enabled,
    is_tool_definitions_enabled,
    is_tool_io_enabled,
    is_metrics_enabled,
    get_max_value_length,
)

logger = logging.getLogger(__name__)

try:  # pragma: no cover
    from opentelemetry.trace import (
        Tracer,
        Span as OtelSpan,
        Status,
        StatusCode,
        set_span_in_context,
    )
    from opentelemetry.context import attach, detach
    from opentelemetry._events import Event
    from opentelemetry.metrics import get_meter
except Exception:  # pragma: no cover
    Tracer = OtelSpan = object  # type: ignore
    Status = StatusCode = object  # type: ignore
    def set_span_in_context(span):  # type: ignore
        return {}

    def attach(ctx):  # type: ignore
        return ctx

    def detach(token):  # type: ignore
        return None

    class Event:  # type: ignore
        def __init__(self, *a, **k):
            pass

    def get_meter(name):  # type: ignore
        class _H:
            def record(self, *a, **k):
                pass

        class _M:
            def create_histogram(self, *a, **k):
                return _H()

        return _M()

PROVIDER_NAME = "gen_ai.provider.name"
OPERATION_NAME = "gen_ai.operation.name"
REQUEST_MODEL = "gen_ai.request.model"
REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
REQUEST_TEMPERATURE = "gen_ai.request.temperature"
REQUEST_TOP_P = "gen_ai.request.top_p"
REQUEST_TOP_K = "gen_ai.request.top_k"
REQUEST_PRESENCE_PENALTY = "gen_ai.request.presence_penalty"
REQUEST_FREQUENCY_PENALTY = "gen_ai.request.frequency_penalty"
REQUEST_STOP_SEQUENCES = "gen_ai.request.stop_sequences"
REQUEST_SEED = "gen_ai.request.seed"
REQUEST_CHOICE_COUNT = "gen_ai.request.choice.count"
REQUEST_ENCODING_FORMATS = "gen_ai.request.encoding_formats"
OUTPUT_TYPE = "gen_ai.output.type"
RESPONSE_ID = "gen_ai.response.id"
RESPONSE_MODEL = "gen_ai.response.model"
RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
CONVERSATION_ID = "gen_ai.conversation.id"
AGENT_ID = "gen_ai.agent.id"
AGENT_NAME = "gen_ai.agent.name"
AGENT_DESCRIPTION = "gen_ai.agent.description"
TOOL_NAME = "gen_ai.tool.name"
TOOL_CALL_ID = "gen_ai.tool.call.id"
TOOL_DESCRIPTION = "gen_ai.tool.description"
TOOL_TYPE = "gen_ai.tool.type"
TOOL_CALL_ARGS = "gen_ai.tool.call.arguments"
TOOL_CALL_RESULT = "gen_ai.tool.call.result"
TOOL_DEFINITIONS = "gen_ai.tool.definitions"
INPUT_MESSAGES = "gen_ai.input.messages"
OUTPUT_MESSAGES = "gen_ai.output.messages"
ORCHESTRATOR_AGENT_DEFS = "gen_ai.orchestrator.agent_definitions"
DATA_SOURCE_ID = "gen_ai.data_source.id"
ERROR_TYPE = "error.type"
SERVER_ADDRESS = "server.address"
SERVER_PORT = "server.port"
OPENAI_REQUEST_SERVICE_TIER = "openai.request.service_tier"
OPENAI_RESPONSE_SERVICE_TIER = "openai.response.service_tier"
OPENAI_RESPONSE_SYSTEM_FINGERPRINT = "openai.response.system_fingerprint"
TOKEN_TYPE = "gen_ai.token.type"
TOKEN_TYPE_INPUT = "input"
TOKEN_TYPE_OUTPUT = "output"


def _first(seq: Iterable[Any], default: Any = None) -> Any:
    for item in seq:
        return item
    return default


def _truncate(value: Any) -> Any:
    max_len = get_max_value_length()
    try:
        s = json.dumps(value, ensure_ascii=False)
        if len(s) <= max_len:
            return value
        return s[: max_len - 3] + "..."
    except Exception:  # pragma: no cover
        return value


def _extract_server_info(client: Any) -> tuple[Optional[str], Optional[int]]:
    base = getattr(client, "base_url", None) or getattr(client, "_base_url", None)
    if not base:
        return None, None
    try:
        from urllib.parse import urlparse
        p = urlparse(str(base))
        host = p.hostname
        port = p.port
        if port == 443:
            port = None
        return host, port
    except Exception:  # pragma: no cover
        return None, None


def _service_tier_from_request(data: Any) -> Optional[str]:
    tier = getattr(data, "service_tier", None)
    if tier and tier != "auto":
        return tier
    cfg = getattr(data, "model_config", None) or {}
    tier = cfg.get("service_tier")
    if tier and tier != "auto":
        return tier
    return None


class GenAISemanticProcessor:  # pragma: no cover
    def __init__(
        self,
        tracer: Optional[Tracer] = None,
        event_logger: Optional[Any] = None,
        include_sensitive_data: bool = False,
        provider_value: str = "openai",
    ) -> None:
        self._tracer = tracer
        self._event_logger = event_logger
        self._capture_content = include_sensitive_data or is_content_enabled()
        self._provider_value = provider_value
        self._root_spans: Dict[str, OtelSpan] = {}
        self._spans: Dict[str, OtelSpan] = {}
        self._ctx_tokens: Dict[str, object] = {}
        self._meter = get_meter(__name__) if is_metrics_enabled() else None
        self._op_duration = None
        self._token_hist = None
        # Active flag allows graceful deactivation when uninstrumenting
        self._active = True
        if self._meter:
            try:  # pragma: no cover
                self._op_duration = self._meter.create_histogram(
                    name="gen_ai.operation.duration", unit="s",
                    description="GenAI operation duration"
                )
                self._token_hist = self._meter.create_histogram(
                    name="gen_ai.token.usage", unit="{token}",
                    description="GenAI token usage counts"
                )
            except Exception:
                self._meter = None

    def on_trace_start(self, trace: Any) -> None:
        if not self._tracer or not self._active:
            return
        try:
            span = self._tracer.start_span(
                name=getattr(trace, "name", "agent.root"),
                attributes={PROVIDER_NAME: self._provider_value},
            )
            self._root_spans[getattr(trace, "trace_id", "")] = span
        except Exception:  # pragma: no cover
            logger.debug("trace start failed", exc_info=True)

    def on_trace_end(self, trace: Any) -> None:
        if not self._active:
            return
        rid = getattr(trace, "trace_id", "")
        root = self._root_spans.pop(rid, None)
        if root:
            try:
                root.set_status(Status(StatusCode.OK))  # type: ignore
                root.end()  # type: ignore
            except Exception:  # pragma: no cover
                pass

    def on_span_start(self, span: Any) -> None:
        if not self._tracer or not self._active:
            return
        try:
            parent_ctx = None
            pid = getattr(span, "parent_id", None)
            if pid and pid in self._spans:
                parent_ctx = set_span_in_context(self._spans[pid])
            elif not pid:
                parent_ctx = set_span_in_context(
                    self._root_spans.get(getattr(span, "trace_id", ""))
                )
            otel_span = self._tracer.start_span(
                name=self._derive_span_name(span),
                context=parent_ctx,
                attributes={PROVIDER_NAME: self._provider_value},
            )
            sid = getattr(span, "span_id", "")
            self._spans[sid] = otel_span
            token = attach(set_span_in_context(otel_span))
            self._ctx_tokens[sid] = token
            setattr(span, "_otel_start", datetime.now(timezone.utc))
        except Exception:  # pragma: no cover
            logger.debug("span start failed", exc_info=True)

    def on_span_end(self, span: Any) -> None:
        if not self._active:
            return
        sid = getattr(span, "span_id", None)
        otel_span = self._spans.pop(sid, None)
        token = self._ctx_tokens.pop(sid, None)
        if token:
            try:
                detach(token)
            except Exception:  # pragma: no cover
                pass
        if not otel_span:
            return
        try:
            attrs = dict(self._extract_attributes(span))
            for k, v in attrs.items():
                if v is not None:
                    otel_span.set_attribute(k, v)  # type: ignore
            err = getattr(span, "error", None)
            if err:
                otel_span.set_status(  # type: ignore
                    Status(
                        StatusCode.ERROR,
                        f"{err.get('message', '')}: {err.get('data', '')}",
                    )
                )
                etype = err.get("type") or err.get("code")
                if etype:
                    otel_span.set_attribute(ERROR_TYPE, etype)  # type: ignore
            else:
                otel_span.set_status(Status(StatusCode.OK))  # type: ignore
            self._emit_events(span, otel_span)
            self._record_metrics(span, attrs, bool(err))
        except Exception:  # pragma: no cover
            logger.debug("span end processing failed", exc_info=True)
        finally:
            try:
                otel_span.end()  # type: ignore
            except Exception:  # pragma: no cover
                pass

    def shutdown(self) -> None:
        self._active = False
        for s in list(self._spans.values()):
            try:
                s.end()  # type: ignore
            except Exception:
                pass
        for s in list(self._root_spans.values()):
            try:
                s.end()  # type: ignore
            except Exception:
                pass
        self._spans.clear()
        self._root_spans.clear()
        self._ctx_tokens.clear()

    # Backwards friendly alias
    def deactivate(self) -> None:  # pragma: no cover
        self.shutdown()

    def _extract_attributes(self, span: Any) -> Iterator[tuple[str, Any]]:
        data = getattr(span, "span_data", span)
        op = self._operation_name(data)
        if op:
            yield OPERATION_NAME, op
        for field, attr in [
            ("model", REQUEST_MODEL),
            ("max_tokens", REQUEST_MAX_TOKENS),
            ("temperature", REQUEST_TEMPERATURE),
            ("top_p", REQUEST_TOP_P),
            ("top_k", REQUEST_TOP_K),
            ("presence_penalty", REQUEST_PRESENCE_PENALTY),
            ("frequency_penalty", REQUEST_FREQUENCY_PENALTY),
            ("stop", REQUEST_STOP_SEQUENCES),
            ("seed", REQUEST_SEED),
            ("response_format", OUTPUT_TYPE),
        ]:
            val = getattr(data, field, None)
            if val is not None:
                if field == "response_format" and isinstance(val, dict):
                    val = val.get("type")
                yield attr, val
        if hasattr(data, "encoding_formats") and getattr(data, "encoding_formats"):
            yield REQUEST_ENCODING_FORMATS, getattr(data, "encoding_formats")
        mc = getattr(data, "model_config", None) or {}
        choice_count = (
            getattr(data, "n", None)
            or mc.get("n")
            or mc.get("choice_count")
        )
        if choice_count and choice_count != 1:
            yield REQUEST_CHOICE_COUNT, choice_count
        st = _service_tier_from_request(data)
        if st:
            yield OPENAI_REQUEST_SERVICE_TIER, st
        client = getattr(data, "client", None)
        if client:
            host, port = _extract_server_info(client)
            if host:
                yield SERVER_ADDRESS, host
            if port:
                yield SERVER_PORT, port
        usage = getattr(data, "usage", None)
        if usage:
            in_t = getattr(usage, "prompt_tokens", None) or getattr(
                usage, "input_tokens", None
            )
            out_t = getattr(usage, "completion_tokens", None) or getattr(
                usage, "output_tokens", None
            )
            if in_t is not None:
                yield USAGE_INPUT_TOKENS, in_t
            if out_t is not None:
                yield USAGE_OUTPUT_TOKENS, out_t
        thread_id = getattr(data, "thread_id", None) or getattr(
            data, "conversation_id", None
        )
        if thread_id:
            yield CONVERSATION_ID, thread_id
        if type(data).__name__ == "AgentSpanData" or hasattr(data, "agent_id"):
            aid = getattr(data, "agent_id", None) or getattr(data, "id", None)
            if aid:
                yield AGENT_ID, aid
            if getattr(data, "name", None):
                yield AGENT_NAME, getattr(data, "name")
            if getattr(data, "description", None):
                yield AGENT_DESCRIPTION, getattr(data, "description")
            if is_tool_definitions_enabled():
                tools = getattr(data, "tools", None)
                if tools:
                    yield TOOL_DEFINITIONS, _truncate(tools)
            agent_defs = getattr(data, "agent_definitions", None)
            if agent_defs:
                yield ORCHESTRATOR_AGENT_DEFS, _truncate(agent_defs)
        if type(data).__name__ == "FunctionSpanData":
            if getattr(data, "name", None):
                yield TOOL_NAME, getattr(data, "name")
            if getattr(data, "call_id", None):
                yield TOOL_CALL_ID, getattr(data, "call_id")
            if getattr(data, "tool_type", None):
                yield TOOL_TYPE, getattr(data, "tool_type")
            if getattr(data, "description", None):
                yield TOOL_DESCRIPTION, getattr(data, "description")
            if is_tool_io_enabled():
                if getattr(data, "input", None) is not None:
                    # Serialize tool arguments as JSON (primitive str attr)
                    try:
                        raw_args = getattr(data, "input")
                        serialized_args = json.dumps(
                            raw_args, ensure_ascii=False
                        )
                    except Exception:  # noqa: BLE001
                        serialized_args = str(getattr(data, "input"))
                    yield TOOL_CALL_ARGS, _truncate(serialized_args)
                if getattr(data, "output", None) is not None:
                    try:
                        raw_res = getattr(data, "output")
                        serialized_res = json.dumps(
                            raw_res, ensure_ascii=False
                        )
                    except Exception:  # noqa: BLE001
                        serialized_res = str(getattr(data, "output"))
                    yield TOOL_CALL_RESULT, _truncate(serialized_res)
        if type(data).__name__ == "ResponseSpanData":
            resp = getattr(data, "response", None)
            if resp is not None:
                if getattr(resp, "id", None):
                    yield RESPONSE_ID, getattr(resp, "id")
                if getattr(resp, "model", None):
                    yield RESPONSE_MODEL, getattr(resp, "model")
                if getattr(resp, "service_tier", None):
                    rst = getattr(resp, "service_tier")
                    if rst and rst != "auto":
                        yield OPENAI_RESPONSE_SERVICE_TIER, rst
                if getattr(resp, "system_fingerprint", None):
                    yield OPENAI_RESPONSE_SYSTEM_FINGERPRINT, getattr(
                        resp, "system_fingerprint"
                    )
                usage2 = getattr(resp, "usage", None)
                if usage2:
                    if getattr(usage2, "prompt_tokens", None) is not None:
                        yield USAGE_INPUT_TOKENS, getattr(
                            usage2, "prompt_tokens"
                        )
                    if getattr(usage2, "completion_tokens", None) is not None:
                        yield USAGE_OUTPUT_TOKENS, getattr(
                            usage2, "completion_tokens"
                        )
                finish = self._finish_reasons(resp)
                if finish:
                    yield RESPONSE_FINISH_REASONS, finish
        if self._capture_content and (
            type(data).__name__ == "AgentSpanData" or hasattr(data, "agent_id")
        ):
            input_msgs = getattr(data, "input", None) or getattr(
                data, "messages", None
            )
            if input_msgs:
                try:
                    yield INPUT_MESSAGES, _truncate(
                        json.dumps(input_msgs, ensure_ascii=False)
                    )
                except Exception:  # noqa: BLE001
                    yield INPUT_MESSAGES, _truncate(str(input_msgs))
            output_msgs = getattr(data, "output", None)
            if output_msgs:
                try:
                    yield OUTPUT_MESSAGES, _truncate(
                        json.dumps(output_msgs, ensure_ascii=False)
                    )
                except Exception:  # noqa: BLE001
                    yield OUTPUT_MESSAGES, _truncate(str(output_msgs))
        if getattr(data, "data_source_id", None):
            yield DATA_SOURCE_ID, getattr(data, "data_source_id")

    def _operation_name(self, data: Any) -> Optional[str]:
        cls = type(data).__name__
    # Any object with 'agent_id' counts as AgentSpanData
        if cls == "AgentSpanData" or hasattr(data, "agent_id"):
            # Prefer explicit flag if provided by upstream
            if getattr(data, "is_creation", False):
                return "create_agent"
            # Heuristic: no parent + description => creation
            if not getattr(data, "parent_id", None) and getattr(
                data, "description", None
            ):
                return "create_agent"
            return "invoke_agent"
        if cls == "FunctionSpanData":
            return "execute_tool"
        if cls == "ResponseSpanData":
            return "chat"
        if cls == "GenerationSpanData":
            first = _first(getattr(data, "input", []) or [])
            if isinstance(first, dict) and "role" in first:
                return "chat"
            return "chat"
        if cls == "EmbeddingsSpanData":
            return "embeddings"
        if cls == "TranscriptionSpanData":
            return "transcription"
        if cls == "SpeechSpanData":
            return "speech_generation"
        if cls == "GuardrailSpanData":
            return "guardrail_check"
        if cls == "HandoffSpanData":
            return "agent_handoff"
        return None

    def _derive_span_name(self, span: Any) -> str:
        data = getattr(span, "span_data", span)
        op = self._operation_name(data) or "operation"
        if op in ("invoke_agent", "create_agent") and getattr(data, "name", None):
            return f"{op} {getattr(data, 'name')}"
        if op == "execute_tool" and getattr(data, "name", None):
            return f"execute_tool {getattr(data, 'name')}"
        if getattr(data, "model", None):
            return f"{op} {getattr(data, 'model')}"
        return op

    def _emit_events(self, span: Any, otel_span: OtelSpan) -> None:
        if not self._event_logger:
            return
        data = getattr(span, "span_data", span)
        ctx = getattr(otel_span, "get_span_context", lambda: None)()
        trace_id = getattr(ctx, "trace_id", 0)
        span_id = getattr(ctx, "span_id", 0)
        flags = getattr(ctx, "trace_flags", 0)
        try:
            evs: list[Event] = []
            if type(data).__name__ == "FunctionSpanData" and is_tool_io_enabled():
                evs.extend(self._function_events(data, trace_id, span_id, flags))
            if type(data).__name__ == "ResponseSpanData" and self._capture_content:
                evs.extend(self._response_events(data, trace_id, span_id, flags))
            for e in evs:
                self._event_logger.emit(e)
        except Exception:  # pragma: no cover
            logger.debug("event emission failed", exc_info=True)

    def _function_events(self, data: Any, trace_id: int, span_id: int, flags: int) -> list[Event]:
        tool_call = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": getattr(data, "call_id", None),
                    "type": "function",
                    "function": {
                        "name": getattr(data, "name", None),
                        "arguments": getattr(data, "input", None),
                    },
                }
            ],
        }
        tool_result = {"role": "tool", "content": getattr(data, "output", None)}
        return [
            Event(
                name="gen_ai.assistant.message",
                attributes={PROVIDER_NAME: self._provider_value},
                body=tool_call,
                trace_id=trace_id,
                span_id=span_id,
                trace_flags=flags,
            ),
            Event(
                name="gen_ai.tool.message",
                attributes={PROVIDER_NAME: self._provider_value},
                body=tool_result,
                trace_id=trace_id,
                span_id=span_id,
                trace_flags=flags,
            ),
        ]

    def _response_events(self, data: Any, trace_id: int, span_id: int, flags: int) -> list[Event]:
        input_msgs = getattr(data, "input", None) or []
        resp = getattr(data, "response", None)
        outputs = getattr(resp, "output", None) or []
        evs: list[Event] = []
        for msg in input_msgs:
            role = msg.get("role", "user") if isinstance(msg, dict) else "user"
            body = msg if isinstance(msg, dict) else {"content": msg}
            evs.append(
                Event(
                    name=f"gen_ai.{role}.message",
                    attributes={PROVIDER_NAME: self._provider_value},
                    body=body,
                    trace_id=trace_id,
                    span_id=span_id,
                    trace_flags=flags,
                )
            )
        for choice in outputs:
            body = {"message": choice if isinstance(choice, dict) else {"content": choice}}
            evs.append(
                Event(
                    name="gen_ai.choice",
                    attributes={PROVIDER_NAME: self._provider_value},
                    body=body,
                    trace_id=trace_id,
                    span_id=span_id,
                    trace_flags=flags,
                )
            )
        return evs

    def _finish_reasons(self, resp: Any) -> Optional[list[str]]:
        fr = getattr(resp, "finish_reasons", None)
        if fr:
            return fr if isinstance(fr, list) else [fr]
        choices = getattr(resp, "choices", None) or []
        out: list[str] = []
        for ch in choices:
            reason = getattr(ch, "finish_reason", None) or getattr(ch, "finish_reasons", None)
            if reason:
                if isinstance(reason, list):
                    out.extend(reason)
                else:
                    out.append(reason)
        return out or None

    def _record_metrics(self, span: Any, attrs: Dict[str, Any], is_error: bool) -> None:
        if not self._meter:
            return
        start = getattr(span, "_otel_start", None)
        if not start:
            return
        try:
            duration = (datetime.now(timezone.utc) - start).total_seconds()
        except Exception:  # pragma: no cover
            return
        metric_attrs: Dict[str, Any] = {PROVIDER_NAME: self._provider_value}
        op = attrs.get(OPERATION_NAME)
        if op:
            metric_attrs[OPERATION_NAME] = op
        model = attrs.get(REQUEST_MODEL)
        if model:
            metric_attrs[REQUEST_MODEL] = model
        if is_error:
            metric_attrs[ERROR_TYPE] = attrs.get(ERROR_TYPE, "error")
        # Duration
        try:
            if self._op_duration:
                self._op_duration.record(duration, metric_attrs)  # type: ignore
        except Exception:  # pragma: no cover
            logger.debug("record duration metric failed", exc_info=True)
        # Token usage
        if not self._token_hist:
            return
        in_tokens = attrs.get(USAGE_INPUT_TOKENS)
        out_tokens = attrs.get(USAGE_OUTPUT_TOKENS)
        try:
            if in_tokens is not None:
                a_in = dict(metric_attrs)
                a_in[TOKEN_TYPE] = TOKEN_TYPE_INPUT
                self._token_hist.record(in_tokens, a_in)  # type: ignore
            if out_tokens is not None:
                a_out = dict(metric_attrs)
                a_out[TOKEN_TYPE] = TOKEN_TYPE_OUTPUT
                self._token_hist.record(out_tokens, a_out)  # type: ignore
        except Exception:  # pragma: no cover
            logger.debug("record token metrics failed", exc_info=True)
