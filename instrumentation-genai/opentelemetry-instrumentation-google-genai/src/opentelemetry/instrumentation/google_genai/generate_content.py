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
# pylint: disable=too-many-lines

import copy
import dataclasses
import functools
import json
import logging
import os
import time
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Iterator,
    Optional,
    Union,
)

from google.genai.models import AsyncModels, Models
from google.genai.models import t as transformers
from google.genai.types import (
    BlockedReason,
    Candidate,
    Content,
    ContentListUnion,
    ContentListUnionDict,
    ContentUnion,
    ContentUnionDict,
    GenerateContentConfig,
    GenerateContentConfigOrDict,
    GenerateContentResponse,
)

from opentelemetry import context as context_api
from opentelemetry import trace
from opentelemetry._logs import LogRecord
from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _StabilityMode,
)
from opentelemetry.semconv._incubating.attributes import (
    code_attributes,
    gen_ai_attributes,
)
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.trace.span import Span
from opentelemetry.util.genai.completion_hook import CompletionHook
from opentelemetry.util.genai.types import (
    ContentCapturingMode,
    InputMessage,
    MessagePart,
    OutputMessage,
)
from opentelemetry.util.genai.utils import gen_ai_json_dumps
from opentelemetry.util.types import (
    AttributeValue,
)

from .allowlist_util import AllowList
from .custom_semconv import GCP_GENAI_OPERATION_CONFIG
from .dict_util import flatten_dict
from .flags import is_content_recording_enabled
from .message import (
    to_input_messages,
    to_output_messages,
    to_system_instructions,
)
from .otel_wrapper import OTelWrapper
from .tool_call_wrapper import wrapped as wrapped_tool

_logger = logging.getLogger(__name__)


# Constant used to make the absence of content more understandable.
_CONTENT_ELIDED = "<elided>"

# Constant used for the value of 'gen_ai.operation.name".
_GENERATE_CONTENT_OP_NAME = "generate_content"

GENERATE_CONTENT_EXTRA_ATTRIBUTES_CONTEXT_KEY = context_api.create_key(
    "generate_content_extra_attributes_context_key"
)


class _MethodsSnapshot:
    def __init__(self):
        self._original_generate_content = Models.generate_content
        self._original_generate_content_stream = Models.generate_content_stream
        self._original_async_generate_content = AsyncModels.generate_content
        self._original_async_generate_content_stream = (
            AsyncModels.generate_content_stream
        )

    @property
    def generate_content(self):
        return self._original_generate_content

    @property
    def generate_content_stream(self):
        return self._original_generate_content_stream

    @property
    def async_generate_content(self):
        return self._original_async_generate_content

    @property
    def async_generate_content_stream(self):
        return self._original_async_generate_content_stream

    def restore(self):
        Models.generate_content = self._original_generate_content
        Models.generate_content_stream = self._original_generate_content_stream
        AsyncModels.generate_content = self._original_async_generate_content
        AsyncModels.generate_content_stream = (
            self._original_async_generate_content_stream
        )


def _get_vertexai_system_name():
    return gen_ai_attributes.GenAiSystemValues.VERTEX_AI.name.lower()


def _get_gemini_system_name():
    return gen_ai_attributes.GenAiSystemValues.GEMINI.name.lower()


def _guess_genai_system_from_env():
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "0").lower() in [
        "true",
        "1",
    ]:
        return _get_vertexai_system_name()
    return _get_gemini_system_name()


def _get_is_vertexai(models_object: Union[Models, AsyncModels]):
    # Since commit 8e561de04965bb8766db87ad8eea7c57c1040442 of "googleapis/python-genai",
    # it is possible to obtain the information using a documented property.
    if hasattr(models_object, "vertexai"):
        vertexai_attr = getattr(models_object, "vertexai")
        if vertexai_attr is not None:
            return vertexai_attr
    # For earlier revisions, it is necessary to deeply inspect the internals.
    if hasattr(models_object, "_api_client"):
        client = getattr(models_object, "_api_client")
        if not client:
            return None
        if hasattr(client, "vertexai"):
            return getattr(client, "vertexai")
    return None


def _determine_genai_system(models_object: Union[Models, AsyncModels]):
    vertexai_attr = _get_is_vertexai(models_object)
    if vertexai_attr is None:
        return _guess_genai_system_from_env()
    if vertexai_attr:
        return _get_vertexai_system_name()
    return _get_gemini_system_name()


def _to_dict(value: object):
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except TypeError:
            return {"ModelName": str(value)}

    return json.loads(json.dumps(value))


def _create_request_attributes(
    config: Optional[GenerateContentConfigOrDict],
    allow_list: AllowList,
) -> dict[str, AttributeValue]:
    if not config:
        return {}
    config = _to_dict(config)
    attributes = flatten_dict(
        config,
        # A custom prefix is used, because the names/structure of the
        # configuration is likely to be specific to Google Gen AI SDK.
        key_prefix=GCP_GENAI_OPERATION_CONFIG,
        exclude_keys=[
            # System instruction can be overly long for a span attribute.
            # Additionally, it is recorded as an event (log), instead.
            "gcp.gen_ai.operation.config.system_instruction",
        ],
        # Although a custom prefix is used by default, some of the attributes
        # are captured in common, standard, Semantic Conventions. For the
        # well-known properties whose values align with Semantic Conventions,
        # we ensure that the key name matches the standard SemConv name.
        rename_keys={
            # TODO: add more entries here as more semantic conventions are
            # generalized to cover more of the available config options.
            "gcp.gen_ai.operation.config.temperature": gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE,
            "gcp.gen_ai.operation.config.top_k": gen_ai_attributes.GEN_AI_REQUEST_TOP_K,
            "gcp.gen_ai.operation.config.top_p": gen_ai_attributes.GEN_AI_REQUEST_TOP_P,
            "gcp.gen_ai.operation.config.candidate_count": gen_ai_attributes.GEN_AI_REQUEST_CHOICE_COUNT,
            "gcp.gen_ai.operation.config.max_output_tokens": gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS,
            "gcp.gen_ai.operation.config.stop_sequences": gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES,
            "gcp.gen_ai.operation.config.frequency_penalty": gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY,
            "gcp.gen_ai.operation.config.presence_penalty": gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY,
            "gcp.gen_ai.operation.config.seed": gen_ai_attributes.GEN_AI_REQUEST_SEED,
        },
    )
    response_mime_type = config.get("response_mime_type")
    if response_mime_type:
        if response_mime_type == "text/plain":
            attributes[gen_ai_attributes.GEN_AI_OUTPUT_TYPE] = "text"
        elif response_mime_type == "application/json":
            attributes[gen_ai_attributes.GEN_AI_OUTPUT_TYPE] = "json"
        else:
            attributes[gen_ai_attributes.GEN_AI_OUTPUT_TYPE] = (
                response_mime_type
            )
    for key in list(attributes.keys()):
        if key.startswith(
            GCP_GENAI_OPERATION_CONFIG
        ) and not allow_list.allowed(key):
            del attributes[key]
    return attributes


def _get_response_property(response: GenerateContentResponse, path: str):
    path_segments = path.split(".")
    current_context = response
    for path_segment in path_segments:
        if current_context is None:
            return None
        if isinstance(current_context, dict):
            current_context = current_context.get(path_segment)
        else:
            current_context = getattr(current_context, path_segment)
    return current_context


def _coerce_config_to_object(
    config: GenerateContentConfigOrDict,
) -> GenerateContentConfig:
    if isinstance(config, GenerateContentConfig):
        return config
    # Input must be a dictionary; convert by invoking the constructor.
    return GenerateContentConfig(**config)


def _wrapped_config_with_tools(
    otel_wrapper: OTelWrapper,
    config: GenerateContentConfig,
    **kwargs,
):
    if not config.tools:
        return config
    result = copy.copy(config)
    result.tools = [
        wrapped_tool(tool, otel_wrapper, **kwargs) for tool in config.tools
    ]
    return result


def _config_to_system_instruction(
    config: Union[GenerateContentConfigOrDict, None],
) -> Union[ContentUnion, None]:
    if not config:
        return None

    if isinstance(config, dict):
        return GenerateContentConfig.model_validate(config).system_instruction
    return config.system_instruction


def _create_completion_details_attributes(
    input_messages: list[InputMessage],
    output_messages: list[OutputMessage],
    system_instructions: list[MessagePart],
    as_str: bool = False,
) -> dict[str, AttributeValue]:
    attributes: dict[str, AttributeValue] = {
        gen_ai_attributes.GEN_AI_INPUT_MESSAGES: [
            dataclasses.asdict(input_message)
            for input_message in input_messages
        ],
        gen_ai_attributes.GEN_AI_OUTPUT_MESSAGES: [
            dataclasses.asdict(output_message)
            for output_message in output_messages
        ],
    }
    if system_instructions:
        attributes[gen_ai_attributes.GEN_AI_SYSTEM_INSTRUCTIONS] = [
            dataclasses.asdict(sys_instr) for sys_instr in system_instructions
        ]

    return attributes


def _get_extra_generate_content_attributes() -> dict[str, AttributeValue]:
    attrs = context_api.get_value(
        GENERATE_CONTENT_EXTRA_ATTRIBUTES_CONTEXT_KEY
    )
    return dict(attrs or {})


class _GenerateContentInstrumentationHelper:
    def __init__(
        self,
        models_object: Union[Models, AsyncModels],
        otel_wrapper: OTelWrapper,
        model: str,
        completion_hook: CompletionHook,
        generate_content_config_key_allowlist: Optional[AllowList] = None,
    ):
        self._start_time = time.time_ns()
        self._otel_wrapper = otel_wrapper
        self._genai_system = _determine_genai_system(models_object)
        self._genai_request_model = model
        self.completion_hook = completion_hook
        self._finish_reasons_set = set()
        self._error_type = None
        self._input_tokens = 0
        self._output_tokens = 0
        self.sem_conv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.GEN_AI
        )
        self._content_recording_enabled = is_content_recording_enabled(
            self.sem_conv_opt_in_mode
        )
        self._response_index = 0
        self._candidate_index = 0
        self._generate_content_config_key_allowlist = (
            generate_content_config_key_allowlist or AllowList()
        )

    def wrapped_config(
        self, config: Optional[GenerateContentConfigOrDict]
    ) -> Optional[GenerateContentConfig]:
        if config is None:
            return None
        return _wrapped_config_with_tools(
            self._otel_wrapper,
            _coerce_config_to_object(config),
            extra_span_attributes={"gen_ai.system": self._genai_system},
        )

    def start_span_as_current_span(
        self, model_name, function_name, end_on_exit=True
    ) -> Span:
        return self._otel_wrapper.start_as_current_span(
            f"{_GENERATE_CONTENT_OP_NAME} {model_name}",
            start_time=self._start_time,
            attributes={
                code_attributes.CODE_FUNCTION_NAME: function_name,
                gen_ai_attributes.GEN_AI_REQUEST_MODEL: self._genai_request_model,
                gen_ai_attributes.GEN_AI_OPERATION_NAME: _GENERATE_CONTENT_OP_NAME,
            },
            end_on_exit=end_on_exit,
        )

    def create_final_attributes(self) -> dict[str, AttributeValue]:
        final_attributes = {
            gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS: self._input_tokens,
            gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS: self._output_tokens,
            gen_ai_attributes.GEN_AI_RESPONSE_FINISH_REASONS: sorted(
                self._finish_reasons_set
            ),
        }
        if self._error_type:
            final_attributes[error_attributes.ERROR_TYPE] = self._error_type
        return final_attributes

    def process_request(
        self,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict],
        span: Span,
    ):
        span.set_attribute(gen_ai_attributes.GEN_AI_SYSTEM, self._genai_system)
        self._maybe_log_system_instruction(config=config)
        self._maybe_log_user_prompt(contents)

    def process_response(self, response: GenerateContentResponse):
        self._update_response(response)
        self._maybe_log_response(response)
        self._response_index += 1

    def process_error(self, e: Exception):
        self._error_type = str(e.__class__.__name__)

    def _update_response(self, response: GenerateContentResponse):
        # TODO: Determine if there are other response properties that
        # need to be reflected back into the span attributes.
        #
        # See also: TODOS.md.
        self._update_finish_reasons(response)
        self._maybe_update_token_counts(response)
        self._maybe_update_error_type(response)

    def _update_finish_reasons(self, response: GenerateContentResponse):
        if not response.candidates:
            return
        for candidate in response.candidates:
            finish_reason = candidate.finish_reason
            if finish_reason is None:
                continue
            finish_reason_str = finish_reason.name.lower().removeprefix(
                "finish_reason_"
            )
            self._finish_reasons_set.add(finish_reason_str)

    def _maybe_update_token_counts(self, response: GenerateContentResponse):
        input_tokens = _get_response_property(
            response, "usage_metadata.prompt_token_count"
        )
        output_tokens = _get_response_property(
            response, "usage_metadata.candidates_token_count"
        )
        if input_tokens and isinstance(input_tokens, int):
            self._input_tokens += input_tokens
        if output_tokens and isinstance(output_tokens, int):
            self._output_tokens += output_tokens

    def _maybe_update_error_type(self, response: GenerateContentResponse):
        if response.candidates:
            return
        if (
            (not response.prompt_feedback)
            or (not response.prompt_feedback.block_reason)
            or (
                response.prompt_feedback.block_reason
                == BlockedReason.BLOCKED_REASON_UNSPECIFIED
            )
        ):
            self._error_type = "NO_CANDIDATES"
            return
        # TODO: in the case where there are no candidate responses due to
        # safety settings like this, it might make sense to emit an event
        # that contains more details regarding the safety settings, their
        # thresholds, etc. However, this requires defining an associated
        # semantic convention to capture this. Follow up with SemConv to
        # establish appropriate data modelling to capture these details,
        # and then emit those details accordingly. (For the time being,
        # we use the defined 'error.type' semantic convention to relay
        # just the minimum amount of error information here).
        #
        # See also: "TODOS.md"
        block_reason = response.prompt_feedback.block_reason.name.upper()
        self._error_type = f"BLOCKED_{block_reason}"

    def _maybe_log_completion_details(
        self,
        extra_attributes: dict[str, AttributeValue],
        request_attributes: dict[str, AttributeValue],
        final_attributes: dict[str, AttributeValue],
        request: Union[ContentListUnion, ContentListUnionDict],
        candidates: list[Candidate],
        config: Optional[GenerateContentConfigOrDict] = None,
    ):
        if (
            self.sem_conv_opt_in_mode
            != _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
        ):
            return
        system_instructions = []
        if system_content := _config_to_system_instruction(config):
            system_instructions = to_system_instructions(
                content=transformers.t_contents(system_content)[0]
            )
        input_messages = to_input_messages(
            contents=transformers.t_contents(request)
        )
        output_messages = to_output_messages(candidates=candidates)

        span = trace.get_current_span()
        event = LogRecord(
            event_name="gen_ai.client.inference.operation.details",
            attributes=extra_attributes
            | request_attributes
            | final_attributes,
        )
        self.completion_hook.on_completion(
            inputs=input_messages,
            outputs=output_messages,
            system_instruction=system_instructions,
            span=span,
            log_record=event,
        )
        completion_details_attributes = _create_completion_details_attributes(
            input_messages,
            output_messages,
            system_instructions,
        )
        if self._content_recording_enabled in [
            ContentCapturingMode.EVENT_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        ]:
            event.attributes = {
                **(event.attributes or {}),
                **completion_details_attributes,
            }
        self._otel_wrapper.log_completion_details(event=event)

        if self._content_recording_enabled in [
            ContentCapturingMode.SPAN_ONLY,
            ContentCapturingMode.SPAN_AND_EVENT,
        ]:
            span.set_attributes(
                {
                    k: gen_ai_json_dumps(v)
                    for k, v in completion_details_attributes.items()
                }
            )
            # request attributes were already set on the span..

    def _maybe_log_system_instruction(
        self, config: Optional[GenerateContentConfigOrDict] = None
    ):
        content_union = _config_to_system_instruction(config)
        if not content_union:
            return
        content = transformers.t_contents(content_union)[0]
        if not content.parts:
            return
        # System instruction is required to be text. An error will be returned by the API if it isn't.
        system_instruction = " ".join(
            part.text for part in content.parts if part.text
        )
        if not system_instruction:
            return
        self._otel_wrapper.log_system_prompt(
            attributes={
                gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
            },
            body={
                "content": (
                    system_instruction
                    if self._content_recording_enabled
                    else _CONTENT_ELIDED
                )
            },
        )

    def _maybe_log_user_prompt(
        self, contents: Union[ContentListUnion, ContentListUnionDict]
    ):
        if isinstance(contents, list):
            total = len(contents)
            index = 0
            for entry in contents:
                self._maybe_log_single_user_prompt(
                    entry, index=index, total=total
                )
                index += 1
        else:
            self._maybe_log_single_user_prompt(contents)

    def _maybe_log_single_user_prompt(
        self, contents: Union[ContentUnion, ContentUnionDict], index=0, total=1
    ):
        # TODO: figure out how to report the index in a manner that is
        # aligned with the OTel semantic conventions.
        attributes = {
            gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
        }

        # TODO: determine if "role" should be reported here or not and, if so,
        # what the value ought to be. It is not clear whether there is always
        # a role supplied (and it looks like there could be cases where there
        # is more than one role present in the supplied contents)?
        #
        # See also: "TODOS.md"
        body = {}
        if self._content_recording_enabled:
            logged_contents = contents
            if isinstance(contents, list):
                logged_contents = Content(parts=contents)
            body["content"] = _to_dict(logged_contents)
        else:
            body["content"] = _CONTENT_ELIDED
        self._otel_wrapper.log_user_prompt(
            attributes=attributes,
            body=body,
        )

    def _maybe_log_response(self, response: GenerateContentResponse):
        self._maybe_log_response_stats(response)
        self._maybe_log_response_safety_ratings(response)
        if not response.candidates:
            return
        candidate_in_response_index = 0
        for candidate in response.candidates:
            self._maybe_log_response_candidate(
                candidate,
                flat_candidate_index=self._candidate_index,
                candidate_in_response_index=candidate_in_response_index,
                response_index=self._response_index,
            )
            self._candidate_index += 1
            candidate_in_response_index += 1

    def _maybe_log_response_candidate(
        self,
        candidate: Candidate,
        flat_candidate_index: int,
        candidate_in_response_index: int,
        response_index: int,
    ):
        # TODO: Determine if there might be a way to report the
        # response index and candidate response index.
        attributes = {
            gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
        }
        # TODO: determine if "role" should be reported here or not and, if so,
        # what the value ought to be.
        #
        # TODO: extract tool information into a separate tool message.
        #
        # TODO: determine if/when we need to emit a 'gen_ai.assistant.message' event.
        #
        # TODO: determine how to report other relevant details in the candidate that
        # are not presently captured by Semantic Conventions. For example, the
        # "citation_metadata", "grounding_metadata", "logprobs_result", etc.
        #
        # See also: "TODOS.md"
        body = {
            "index": flat_candidate_index,
        }
        if self._content_recording_enabled:
            if candidate.content:
                body["content"] = _to_dict(candidate.content)
        else:
            body["content"] = _CONTENT_ELIDED
        if candidate.finish_reason is not None:
            body["finish_reason"] = candidate.finish_reason.name
        self._otel_wrapper.log_response_content(
            attributes=attributes,
            body=body,
        )

    def _maybe_log_response_stats(self, response: GenerateContentResponse):
        # TODO: Determine if there is a way that we can log a summary
        # of the overall response in a manner that is aligned with
        # Semantic Conventions. For example, it would be natural
        # to report an event that looks something like:
        #
        #      gen_ai.response.stats {
        #         response_index: 0,
        #         candidate_count: 3,
        #         parts_per_candidate: [
        #            3,
        #            1,
        #            5
        #         ]
        #      }
        #
        pass

    def _maybe_log_response_safety_ratings(
        self, response: GenerateContentResponse
    ):
        # TODO: Determine if there is a way that we can log
        # the "prompt_feedback". This would be especially useful
        # in the case where the response is blocked.
        pass

    def _record_token_usage_metric(self):
        self._otel_wrapper.token_usage_metric.record(
            self._input_tokens,
            attributes={
                gen_ai_attributes.GEN_AI_TOKEN_TYPE: "input",
                gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
                gen_ai_attributes.GEN_AI_REQUEST_MODEL: self._genai_request_model,
                gen_ai_attributes.GEN_AI_OPERATION_NAME: _GENERATE_CONTENT_OP_NAME,
            },
        )
        self._otel_wrapper.token_usage_metric.record(
            self._output_tokens,
            attributes={
                gen_ai_attributes.GEN_AI_TOKEN_TYPE: "output",
                gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
                gen_ai_attributes.GEN_AI_REQUEST_MODEL: self._genai_request_model,
                gen_ai_attributes.GEN_AI_OPERATION_NAME: _GENERATE_CONTENT_OP_NAME,
            },
        )

    def _record_duration_metric(self):
        attributes = {
            gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
            gen_ai_attributes.GEN_AI_REQUEST_MODEL: self._genai_request_model,
            gen_ai_attributes.GEN_AI_OPERATION_NAME: _GENERATE_CONTENT_OP_NAME,
        }
        if self._error_type is not None:
            attributes[error_attributes.ERROR_TYPE] = self._error_type
        duration_nanos = time.time_ns() - self._start_time
        duration_seconds = duration_nanos / 1e9
        self._otel_wrapper.operation_duration_metric.record(
            duration_seconds,
            attributes=attributes,
        )


def _create_instrumented_generate_content(
    snapshot: _MethodsSnapshot,
    otel_wrapper: OTelWrapper,
    completion_hook: CompletionHook,
    generate_content_config_key_allowlist: Optional[AllowList] = None,
):
    wrapped_func = snapshot.generate_content

    @functools.wraps(wrapped_func)
    def instrumented_generate_content(
        self: Models,
        *,
        model: str,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict] = None,
        **kwargs: Any,
    ) -> GenerateContentResponse:
        candidates = []
        helper = _GenerateContentInstrumentationHelper(
            self,
            otel_wrapper,
            model,
            completion_hook,
            generate_content_config_key_allowlist=generate_content_config_key_allowlist,
        )
        request_attributes = _create_request_attributes(
            config,
            helper._generate_content_config_key_allowlist,
        )
        with helper.start_span_as_current_span(
            model, "google.genai.Models.generate_content"
        ) as span:
            extra_attributes = _get_extra_generate_content_attributes()
            span.set_attributes(extra_attributes | request_attributes)
            if helper.sem_conv_opt_in_mode == _StabilityMode.DEFAULT:
                helper.process_request(contents, config, span)
            try:
                response = wrapped_func(
                    self,
                    model=model,
                    contents=contents,
                    config=helper.wrapped_config(config),
                    **kwargs,
                )
                if (
                    helper.sem_conv_opt_in_mode
                    == _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
                ):
                    helper._update_response(response)
                    if response.candidates:
                        candidates += response.candidates

                else:
                    helper.process_response(response)
                return response
            except Exception as error:
                helper.process_error(error)
                raise
            finally:
                final_attributes = helper.create_final_attributes()
                span.set_attributes(final_attributes)
                helper._maybe_log_completion_details(
                    extra_attributes,
                    request_attributes,
                    final_attributes,
                    contents,
                    candidates,
                    config,
                )
                helper._record_token_usage_metric()
                helper._record_duration_metric()

    return instrumented_generate_content


def _create_instrumented_generate_content_stream(
    snapshot: _MethodsSnapshot,
    otel_wrapper: OTelWrapper,
    completion_hook: CompletionHook,
    generate_content_config_key_allowlist: Optional[AllowList] = None,
):
    wrapped_func = snapshot.generate_content_stream

    @functools.wraps(wrapped_func)
    def instrumented_generate_content_stream(
        self: Models,
        *,
        model: str,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict] = None,
        **kwargs: Any,
    ) -> Iterator[GenerateContentResponse]:
        candidates: list[Candidate] = []
        helper = _GenerateContentInstrumentationHelper(
            self,
            otel_wrapper,
            model,
            completion_hook,
            generate_content_config_key_allowlist=generate_content_config_key_allowlist,
        )
        request_attributes = _create_request_attributes(
            config,
            helper._generate_content_config_key_allowlist,
        )
        with helper.start_span_as_current_span(
            model, "google.genai.Models.generate_content_stream"
        ) as span:
            extra_attributes = _get_extra_generate_content_attributes()
            span.set_attributes(extra_attributes | request_attributes)
            if helper.sem_conv_opt_in_mode == _StabilityMode.DEFAULT:
                helper.process_request(contents, config, span)
            try:
                for response in wrapped_func(
                    self,
                    model=model,
                    contents=contents,
                    config=helper.wrapped_config(config),
                    **kwargs,
                ):
                    if (
                        helper.sem_conv_opt_in_mode
                        == _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
                    ):
                        helper._update_response(response)
                        if response.candidates:
                            candidates += response.candidates

                    else:
                        helper.process_response(response)
                    yield response
            except Exception as error:
                helper.process_error(error)
                raise
            finally:
                final_attributes = helper.create_final_attributes()
                span.set_attributes(final_attributes)
                helper._maybe_log_completion_details(
                    extra_attributes,
                    request_attributes,
                    final_attributes,
                    contents,
                    candidates,
                    config,
                )
                helper._record_token_usage_metric()
                helper._record_duration_metric()

    return instrumented_generate_content_stream


def _create_instrumented_async_generate_content(
    snapshot: _MethodsSnapshot,
    otel_wrapper: OTelWrapper,
    completion_hook: CompletionHook,
    generate_content_config_key_allowlist: Optional[AllowList] = None,
):
    wrapped_func = snapshot.async_generate_content

    @functools.wraps(wrapped_func)
    async def instrumented_generate_content(
        self: AsyncModels,
        *,
        model: str,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict] = None,
        **kwargs: Any,
    ) -> GenerateContentResponse:
        helper = _GenerateContentInstrumentationHelper(
            self,
            otel_wrapper,
            model,
            completion_hook,
            generate_content_config_key_allowlist=generate_content_config_key_allowlist,
        )
        request_attributes = _create_request_attributes(
            config,
            helper._generate_content_config_key_allowlist,
        )
        candidates: list[Candidate] = []
        with helper.start_span_as_current_span(
            model, "google.genai.AsyncModels.generate_content"
        ) as span:
            extra_attributes = _get_extra_generate_content_attributes()
            span.set_attributes(extra_attributes | request_attributes)
            if helper.sem_conv_opt_in_mode == _StabilityMode.DEFAULT:
                helper.process_request(contents, config, span)
            try:
                response = await wrapped_func(
                    self,
                    model=model,
                    contents=contents,
                    config=helper.wrapped_config(config),
                    **kwargs,
                )
                if (
                    helper.sem_conv_opt_in_mode
                    == _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
                ):
                    helper._update_response(response)
                    if response.candidates:
                        candidates += response.candidates
                else:
                    helper.process_response(response)
                return response
            except Exception as error:
                helper.process_error(error)
                raise
            finally:
                final_attributes = helper.create_final_attributes()
                span.set_attributes(final_attributes)
                helper._maybe_log_completion_details(
                    extra_attributes,
                    request_attributes,
                    final_attributes,
                    contents,
                    candidates,
                    config,
                )
                helper._record_token_usage_metric()
                helper._record_duration_metric()

    return instrumented_generate_content


# Disabling type checking because this is not yet implemented and tested fully.
def _create_instrumented_async_generate_content_stream(  # type: ignore
    snapshot: _MethodsSnapshot,
    otel_wrapper: OTelWrapper,
    completion_hook: CompletionHook,
    generate_content_config_key_allowlist: Optional[AllowList] = None,
):
    wrapped_func = snapshot.async_generate_content_stream

    @functools.wraps(wrapped_func)
    async def instrumented_generate_content_stream(
        self: AsyncModels,
        *,
        model: str,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict] = None,
        **kwargs: Any,
    ) -> Awaitable[AsyncIterator[GenerateContentResponse]]:  # type: ignore
        helper = _GenerateContentInstrumentationHelper(
            self,
            otel_wrapper,
            model,
            completion_hook,
            generate_content_config_key_allowlist=generate_content_config_key_allowlist,
        )
        request_attributes = _create_request_attributes(
            config,
            helper._generate_content_config_key_allowlist,
        )
        with helper.start_span_as_current_span(
            model,
            "google.genai.AsyncModels.generate_content_stream",
            end_on_exit=False,
        ) as span:
            extra_attributes = _get_extra_generate_content_attributes()
            span.set_attributes(extra_attributes | request_attributes)
            if (
                not helper.sem_conv_opt_in_mode
                == _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
            ):
                helper.process_request(contents, config, span)
            try:
                response_async_generator = await wrapped_func(
                    self,
                    model=model,
                    contents=contents,
                    config=helper.wrapped_config(config),
                    **kwargs,
                )
            except Exception as error:  # pylint: disable=broad-exception-caught
                helper.process_error(error)
                helper._record_token_usage_metric()
                final_attributes = helper.create_final_attributes()
                span.set_attributes(final_attributes)
                helper._maybe_log_completion_details(
                    extra_attributes,
                    request_attributes,
                    final_attributes,
                    contents,
                    [],
                    config,
                )
                helper._record_duration_metric()
                with trace.use_span(span, end_on_exit=True):
                    raise

            async def _response_async_generator_wrapper():
                candidates: list[Candidate] = []
                with trace.use_span(span, end_on_exit=True):
                    try:
                        async for response in response_async_generator:
                            if (
                                helper.sem_conv_opt_in_mode
                                == _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL
                            ):
                                helper._update_response(response)
                                if response.candidates:
                                    candidates += response.candidates

                            else:
                                helper.process_response(response)
                            yield response
                    except Exception as error:
                        helper.process_error(error)
                        raise
                    finally:
                        final_attributes = helper.create_final_attributes()
                        span.set_attributes(final_attributes)
                        helper._maybe_log_completion_details(
                            extra_attributes,
                            request_attributes,
                            final_attributes,
                            contents,
                            candidates,
                            config,
                        )
                        helper._record_token_usage_metric()
                        helper._record_duration_metric()

            return _response_async_generator_wrapper()

    return instrumented_generate_content_stream


def uninstrument_generate_content(snapshot: object):
    assert isinstance(snapshot, _MethodsSnapshot)
    snapshot.restore()


def instrument_generate_content(
    otel_wrapper: OTelWrapper,
    completion_hook: CompletionHook,
    generate_content_config_key_allowlist: Optional[AllowList] = None,
) -> object:
    opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
        _OpenTelemetryStabilitySignalType.GEN_AI
    )
    if opt_in_mode not in (
        _StabilityMode.GEN_AI_LATEST_EXPERIMENTAL,
        _StabilityMode.DEFAULT,
    ):
        raise ValueError(f"Sem Conv opt in mode {opt_in_mode} not supported.")
    snapshot = _MethodsSnapshot()
    Models.generate_content = _create_instrumented_generate_content(
        snapshot,
        otel_wrapper,
        completion_hook,
        generate_content_config_key_allowlist=generate_content_config_key_allowlist,
    )
    Models.generate_content_stream = _create_instrumented_generate_content_stream(
        snapshot,
        otel_wrapper,
        completion_hook,
        generate_content_config_key_allowlist=generate_content_config_key_allowlist,
    )
    AsyncModels.generate_content = _create_instrumented_async_generate_content(
        snapshot,
        otel_wrapper,
        completion_hook,
        generate_content_config_key_allowlist=generate_content_config_key_allowlist,
    )
    AsyncModels.generate_content_stream = _create_instrumented_async_generate_content_stream(
        snapshot,
        otel_wrapper,
        completion_hook,
        generate_content_config_key_allowlist=generate_content_config_key_allowlist,
    )
    return snapshot
