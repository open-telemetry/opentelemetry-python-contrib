# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class LLMSpanAttributes(BaseModel):
    model_config = ConfigDict(extra="allow")
    gen_ai_operation_name: str = Field(
        ...,
        alias="gen_ai.operation.name",
        description="The name of the operation being performed.",
    )
    gen_ai_request_model: str = Field(
        ...,
        alias="gen_ai.request.model",
        description="Model name from the input request",
    )
    gen_ai_response_model: Optional[str] = Field(
        None,
        alias="gen_ai.response.model",
        description="Model name from the response",
    )
    gen_ai_request_temperature: Optional[float] = Field(
        None,
        alias="gen_ai.request.temperature",
        description="Temperature value from the input request",
    )
    gen_ai_request_logit_bias: Optional[Dict[str, int]] = Field(
        None,
        alias="gen_ai.request.logit_bias",
        description="Likelihood bias of the specified tokens the input request.",
    )
    gen_ai_request_logprobs: Optional[bool] = Field(
        None,
        alias="gen_ai.request.logprobs",
        description="Logprobs flag returns log probabilities.",
    )
    gen_ai_request_top_logprobs: Optional[float] = Field(
        None,
        alias="gen_ai.request.top_logprobs",
        description="Integer between 0 and 5 specifying the number of most likely tokens to return.",
    )
    gen_ai_request_top_p: Optional[float] = Field(
        None,
        alias="gen_ai.request.top_p",
        description="Top P value from the input request",
    )
    gen_ai_request_top_k: Optional[float] = Field(
        None,
        alias="gen_ai.request.top_k",
        description="Top K results to return from the input request",
    )
    gen_ai_user: Optional[str] = Field(
        None, alias="gen_ai.user", description="User ID from the input request"
    )
    gen_ai_prompt: Optional[str] = Field(
        None,
        alias="gen_ai.prompt",
        description="Prompt text from the input request",
    )
    gen_ai_completion: Optional[str] = Field(
        None,
        alias="gen_ai.completion",
        description='Completion text from the response. This will be an array of json objects with the following format {"role": "", "content": ""}. Role can be one of the following values: [system, user, assistant, tool]',
    )
    gen_ai_request_stream: Optional[bool] = Field(
        None,
        alias="gen_ai.request.stream",
        description="Stream flag from the input request",
    )
    gen_ai_request_encoding_formats: Optional[List[str]] = Field(
        None,
        alias="gen_ai.request.encoding_formats",
        description="Encoding formats from the input request. Allowed values: ['float', 'int8','uint8', 'binary', 'ubinary', 'base64']",
    )
    gen_ai_completion_chunk: Optional[str] = Field(
        None,
        alias="gen_ai.completion.chunk",
        description="Chunk text from the response",
    )
    gen_ai_response_finish_reasons: Optional[List[str]] = Field(
        None,
        alias="gen_ai.response.finish_reasons",
        description="Array of reasons the model stopped generating tokens, corresponding to each generation received",
    )
    gen_ai_system_fingerprint: Optional[str] = Field(
        None,
        alias="gen_ai.system_fingerprint",
        description="System fingerprint of the system that generated the response",
    )
    gen_ai_request_tool_choice: Optional[str] = Field(
        None,
        alias="gen_ai.request.tool_choice",
        description="Tool choice from the input request",
    )
    gen_ai_response_tool_calls: Optional[str] = Field(
        None,
        alias="gen_ai.response.tool_calls",
        description="Array of tool calls from the response json stringified",
    )
    gen_ai_request_max_tokens: Optional[float] = Field(
        None,
        alias="gen_ai.request.max_tokens",
        description="The maximum number of tokens the LLM generates for a request.",
    )
    gen_ai_usage_input_tokens: Optional[float] = Field(
        None,
        alias="gen_ai.usage.input_tokens",
        description="The number of tokens used in the llm prompt.",
    )
    gen_ai_usage_total_tokens: Optional[float] = Field(
        None,
        alias="gen_ai.usage.total_tokens",
        description="The total number of tokens used in the llm request.",
    )
    gen_ai_usage_output_tokens: Optional[float] = Field(
        None,
        alias="gen_ai.usage.output_tokens",
        description="The number of tokens in the llm response.",
    )
    gen_ai_request_seed: Optional[str] = Field(
        None,
        alias="gen_ai.request.seed",
        description="Seed from the input request",
    )
    gen_ai_request_frequency_penalty: Optional[float] = Field(
        None,
        alias="gen_ai.request.frequency_penalty",
        description="Frequency penalty from the input request",
    )
    gen_ai_request_presence_penalty: Optional[float] = Field(
        None,
        alias="gen_ai.request.presence_penalty",
        description="Presence penalty from the input request",
    )
    gen_ai_request_tools: Optional[str] = Field(
        None,
        alias="gen_ai.request.tools",
        description="An array of tools from the input request json stringified",
    )
    gen_ai_request_tool_results: Optional[str] = Field(
        None,
        alias="gen_ai.request.tool_results",
        description="An array of tool results from the input request json stringified",
    )
