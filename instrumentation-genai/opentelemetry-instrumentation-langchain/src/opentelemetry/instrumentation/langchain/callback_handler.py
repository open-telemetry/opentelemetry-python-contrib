import time
from dataclasses import dataclass, field
from typing import Any, Optional
from langchain_core.callbacks import (
    BaseCallbackHandler,
)

from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from opentelemetry.trace import SpanKind, set_span_in_context
from opentelemetry.trace.span import Span
from opentelemetry.util.types import AttributeValue
from uuid import UUID

from opentelemetry import context as context_api
from opentelemetry.instrumentation.utils import _SUPPRESS_INSTRUMENTATION_KEY

from langchain_core.agents import AgentAction, AgentFinish

from opentelemetry.instrumentation.langchain.span_attributes import Span_Attributes, GenAIOperationValues
from opentelemetry.trace.status import Status, StatusCode

@dataclass
class SpanHolder:
    span: Span
    children: list[UUID]
    start_time: float = field(default_factory=time.time())
    request_model: Optional[str] = None
    
def _set_request_params(span, kwargs, span_holder: SpanHolder):
        
    for model_tag in ("model_id", "base_model_id"):
        if (model := kwargs.get(model_tag)) is not None:
            span_holder.request_model = model
            break
        elif (
            model := (kwargs.get("invocation_params") or {}).get(model_tag)
        ) is not None:
            span_holder.request_model = model
            break
    else:
        model = "unknown"
    
    if span_holder.request_model is None:
        model = None

    _set_span_attribute(span, Span_Attributes.GEN_AI_REQUEST_MODEL, model)
    _set_span_attribute(span, Span_Attributes.GEN_AI_RESPONSE_MODEL, model)

    if "invocation_params" in kwargs:
        params = (
            kwargs["invocation_params"].get("params") or kwargs["invocation_params"]
        )
    else:
        params = kwargs

    _set_span_attribute(
        span,
        Span_Attributes.GEN_AI_REQUEST_MAX_TOKENS,
        params.get("max_tokens") or params.get("max_new_tokens"),
    )
    
    _set_span_attribute(
        span, Span_Attributes.GEN_AI_REQUEST_TEMPERATURE, params.get("temperature")
    )

    _set_span_attribute(span, Span_Attributes.GEN_AI_REQUEST_TOP_P, params.get("top_p"))

       
def _set_span_attribute(span: Span, name: str, value: AttributeValue):
    if value is not None and value != "":
        span.set_attribute(name, value)

        
def _sanitize_metadata_value(value: Any) -> Any:
    """Convert metadata values to OpenTelemetry-compatible types."""
    if value is None:
        return None
    if isinstance(value, (bool, str, bytes, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [str(_sanitize_metadata_value(v)) for v in value]
    return str(value)

class OpenTelemetryCallbackHandler(BaseCallbackHandler):
    def __init__(self, tracer):
        super().__init__()
        self.tracer = tracer
        self.span_mapping: dict[UUID, SpanHolder] = {}


    def _end_span(self, span: Span, run_id: UUID) -> None:
        for child_id in self.span_mapping[run_id].children:
            child_span = self.span_mapping[child_id].span
            if child_span.end_time is None:
                child_span.end()
        span.end()
        

    def _create_span(
            self,
            run_id: UUID,
            parent_run_id: Optional[UUID],
            span_name: str,
            kind: SpanKind = SpanKind.INTERNAL,
            metadata: Optional[dict[str, Any]] = None,
        ) -> Span:
        
            metadata = metadata or {}
            
            if metadata is not None:
                current_association_properties = (
                    context_api.get_value("association_properties") or {}
                )
                sanitized_metadata = {
                    k: _sanitize_metadata_value(v)
                    for k, v in metadata.items()
                    if v is not None
                }
                context_api.attach(
                    context_api.set_value(
                        "association_properties",
                        {**current_association_properties, **sanitized_metadata},
                    )
                )

            if parent_run_id is not None and parent_run_id in self.span_mapping:
                span = self.tracer.start_span(
                    span_name,
                    context=set_span_in_context(self.span_mapping[parent_run_id].span),
                    kind=kind,
                )
            else:
                span = self.tracer.start_span(span_name, kind=kind)
                _set_span_attribute(span, "root_span", True)

            model_id = "unknown"
            
            if "invocation_params" in metadata:
                if "base_model_id" in metadata["invocation_params"]:
                    model_id = metadata["invocation_params"]["base_model_id"]
                elif "model_id" in metadata["invocation_params"]:
                    model_id = metadata["invocation_params"]["model_id"]

            self.span_mapping[run_id] = SpanHolder(
                span, [], time.time(), model_id
            )

            if parent_run_id is not None and parent_run_id in self.span_mapping:
                self.span_mapping[parent_run_id].children.append(run_id)

            return span
    
    
    @staticmethod
    def _get_name_from_callback(
        serialized: dict[str, Any],
        _tags: Optional[list[str]] = None,
        _metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Get the name to be used for the span. Based on heuristic. Can be extended."""
        if serialized and "kwargs" in serialized and serialized["kwargs"].get("name"):
            return serialized["kwargs"]["name"]
        if kwargs.get("name"):
            return kwargs["name"]
        if serialized.get("name"):
            return serialized["name"]
        if "id" in serialized:
            return serialized["id"][-1]

        return "unknown"
    

    def _handle_error(
        self,
        error: BaseException,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Common error handling logic for all components."""
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        span = self.span_mapping[run_id].span
        span.set_status(Status(StatusCode.ERROR))
        span.record_exception(error)
        self._end_span(span, run_id)


    def on_chat_model_start(self, 
                            serialized: dict[str, Any],
                            messages: list[list[BaseMessage]],
                            *, 
                            run_id: UUID, 
                            tags: Optional[list[str]] = None, 
                            parent_run_id: Optional[UUID] = None, 
                            metadata: Optional[dict[str, Any]] = None, 
                            **kwargs: Any
                            ):
        
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return
        model_id = None
        if "invocation_params" in kwargs and "model_id" in kwargs["invocation_params"]:
            model_id = kwargs["invocation_params"]["model_id"]
        
        name = self._get_name_from_callback(serialized, kwargs=kwargs)
        if model_id != None:
            name = model_id
        
        span = self._create_span(
            run_id,
            parent_run_id,
            f"{GenAIOperationValues.CHAT} {name}",
            kind=SpanKind.CLIENT,
            metadata=metadata,
        )
        _set_span_attribute(span, Span_Attributes.GEN_AI_OPERATION_NAME, GenAIOperationValues.CHAT)
        
        
        if "kwargs" in serialized:
            _set_request_params(span, serialized["kwargs"], self.span_mapping[run_id])
        if "name" in serialized:
            _set_span_attribute(span, Span_Attributes.GEN_AI_SYSTEM, serialized.get("name"))
        _set_span_attribute(span, Span_Attributes.GEN_AI_OPERATION_NAME, "chat")
        

    def on_llm_start(self, 
                     serialized: dict[str, Any], 
                     prompts: list[str], 
                     *, 
                     run_id: UUID, 
                     parent_run_id: UUID | None = None,
                     tags: Optional[list[str]] | None = None,
                     metadata: Optional[dict[str,Any]] | None = None,
                     **kwargs: Any
                     ):        
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return
        
        model_id = None
        if "invocation_params" in kwargs and "model_id" in kwargs["invocation_params"]:
            model_id = kwargs["invocation_params"]["model_id"]
            
        name = self._get_name_from_callback(serialized, kwargs=kwargs)
        if model_id != None:
            name = model_id
        
        span = self._create_span(
            run_id,
            parent_run_id,
            f"{GenAIOperationValues.CHAT} {name}",
            kind=SpanKind.CLIENT,
            metadata=metadata,
        )
        _set_span_attribute(span, Span_Attributes.GEN_AI_OPERATION_NAME, GenAIOperationValues.CHAT)

        _set_request_params(span, kwargs, self.span_mapping[run_id])
        
        _set_span_attribute(span, Span_Attributes.GEN_AI_SYSTEM, serialized.get("name"))

        _set_span_attribute(span, Span_Attributes.GEN_AI_OPERATION_NAME, "text_completion")
         

    def on_llm_end(self, 
                   response: LLMResult, 
                   *, 
                   run_id: UUID, 
                   parent_run_id: UUID | None = None, 
                   tags: Optional[list[str]] | None = None,
                   **kwargs: Any
                   ):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        span = None
        if run_id in self.span_mapping:
            span = self.span_mapping[run_id].span
        else:
            return

        model_name = None
        if response.llm_output is not None:
            model_name = response.llm_output.get(
                "model_name"
            ) or response.llm_output.get("model_id")
            if model_name is not None:
                _set_span_attribute(span, Span_Attributes.GEN_AI_RESPONSE_MODEL, model_name)
                
            id = response.llm_output.get("id")
            if id is not None and id != "":
                _set_span_attribute(span, Span_Attributes.GEN_AI_RESPONSE_ID, id)

        token_usage = (response.llm_output or {}).get("token_usage") or (
            response.llm_output or {}
        ).get("usage")
        
        if token_usage is not None:
            prompt_tokens = (
                token_usage.get("prompt_tokens")
                or token_usage.get("input_token_count")
                or token_usage.get("input_tokens")
            )
            completion_tokens = (
                token_usage.get("completion_tokens")
                or token_usage.get("generated_token_count")
                or token_usage.get("output_tokens")
            )
            
            _set_span_attribute(
                span, Span_Attributes.GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens
            )
        
            _set_span_attribute(
                span, Span_Attributes.GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens
            )
        
        self._end_span(span, run_id)

    def on_llm_error(self, 
                     error: BaseException, 
                     *, 
                     run_id: UUID, 
                     parent_run_id: UUID | None = None, 
                     tags: Optional[list[str]] | None = None,
                     **kwargs: Any
                     ):
        self._handle_error(error, run_id, parent_run_id, **kwargs)


    def on_chain_start(self, 
                       serialized: dict[str, Any], 
                       inputs: dict[str, Any], 
                       *, 
                       run_id: UUID, 
                       parent_run_id: UUID | None = None, 
                       tags: Optional[list[str]] | None = None, 
                       metadata: Optional[dict[str,Any]] | None = None, 
                       **kwargs: Any
                       ):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return
        
            
        name = self._get_name_from_callback(serialized, **kwargs)

        span_name = f"chain {name}"
        span = self._create_span(
            run_id,
            parent_run_id,
            span_name,
            metadata=metadata,
        )        
        
        if "agent_name" in metadata:
            _set_span_attribute(span, Span_Attributes.GEN_AI_AGENT_NAME, metadata["agent_name"])
            
        _set_span_attribute(span, "gen_ai.prompt", str(inputs))
        
            
    def on_chain_end(self, 
                     outputs: dict[str, Any], 
                     *, 
                     run_id: UUID, 
                     parent_run_id: UUID | None = None, 
                     tags: list[str] | None = None,
                     **kwargs: Any
                     ):   
    
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return       
        
        span_holder = self.span_mapping[run_id]
        span = span_holder.span
        _set_span_attribute(span, "gen_ai.completion", str(outputs))
        self._end_span(span, run_id)


    def on_chain_error(self, 
                       error: BaseException, 
                       run_id: UUID, 
                       parent_run_id: UUID | None = None, 
                       tags: Optional[list[str]] | None = None, 
                       **kwargs: Any
                       ):
        self._handle_error(error, run_id, parent_run_id, **kwargs)
        
        
    def on_tool_start(self, 
                      serialized: dict[str, Any], 
                      input_str: str, 
                      *, 
                      run_id: UUID, 
                      parent_run_id: UUID | None = None, 
                      tags: list[str] | None = None, 
                      metadata: dict[str, Any] | None = None, 
                      inputs: dict[str, Any] | None = None, 
                      **kwargs: Any
                      ):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return
        
        
        name = self._get_name_from_callback(serialized, kwargs=kwargs)
        span_name = f"execute_tool {name}"
        span = self._create_span(
            run_id,
            parent_run_id,
            span_name,
            metadata=metadata,
        )
        
        _set_span_attribute(span, "gen_ai.tool.input", input_str)
        
        if serialized.get("id"):
            _set_span_attribute(
                span,
                Span_Attributes.GEN_AI_TOOL_CALL_ID,
                serialized.get("id")
            )
            
        if serialized.get("description"):
            _set_span_attribute(
                span,
                Span_Attributes.GEN_AI_TOOL_DESCRIPTION,
                serialized.get("description"),
            )
            
        _set_span_attribute(
            span,
            Span_Attributes.GEN_AI_TOOL_NAME,
            name
        )
        
        _set_span_attribute(span, Span_Attributes.GEN_AI_OPERATION_NAME, "execute_tool")
    

    def on_tool_end(self, 
                    output: Any, 
                    *, 
                    run_id: UUID, 
                    parent_run_id: UUID | None = None,
                    tags: list[str] | None = None,
                    **kwargs: Any
                    ):
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return

        span = self.span_mapping[run_id].span
        
        _set_span_attribute(span, "gen_ai.tool.output", str(output))
        self._end_span(span, run_id)
    
    
    def on_tool_error(self,
                      error: BaseException, 
                      run_id: UUID, 
                      parent_run_id: UUID| None = None, 
                      tags: list[str] | None = None,
                      **kwargs: Any,
                      ):
        self._handle_error(error, run_id, parent_run_id, **kwargs)
    
    
    def on_agent_action(self,
                    action: AgentAction,
                    run_id: UUID,
                    parent_run_id: UUID,
                    **kwargs: Any
                    ):
        tool = getattr(action, "tool", None)
        tool_input = getattr(action, "tool_input", None)

        if run_id in self.span_mapping:
            span = self.span_mapping[run_id].span
        
            _set_span_attribute(span, "gen_ai.agent.tool.input", tool_input)
            _set_span_attribute(span, "gen_ai.agent.tool.name", tool)
            _set_span_attribute(span, Span_Attributes.GEN_AI_OPERATION_NAME, "invoke_agent")
    
    def on_agent_finish(self, 
                        finish: AgentFinish, 
                        run_id: UUID, 
                        parent_run_id: UUID, 
                        **kwargs: Any
                        ):
        
        span = self.span_mapping[run_id].span
        
        _set_span_attribute(span, "gen_ai.agent.tool.output", finish.return_values['output'])


    def on_agent_error(self, error, run_id, parent_run_id, **kwargs):
        self._handle_error(error, run_id, parent_run_id, **kwargs)