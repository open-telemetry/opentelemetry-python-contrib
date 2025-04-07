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

import functools
import json
import logging
import os
import time
from typing import Any, AsyncIterator, Awaitable, Iterator, Optional, Union

from google.genai.models import AsyncModels, Models
from google.genai.types import (
    BlockedReason,
    Candidate,
    Content,
    ContentListUnion,
    ContentListUnionDict,
    ContentUnion,
    ContentUnionDict,
    GenerateContentConfigOrDict,
    GenerateContentResponse,
)

from opentelemetry import trace
from opentelemetry.semconv._incubating.attributes import (
    code_attributes,
    gen_ai_attributes,
)
from opentelemetry.semconv.attributes import error_attributes

from .allowlist_util import AllowList
from .custom_semconv import CUSTOM_LLM_REQUEST_PREFIX
from .dict_util import flatten_dict
from .flags import is_content_recording_enabled
from .otel_wrapper import OTelWrapper

_logger = logging.getLogger(__name__)


# Constant used to make the absence of content more understandable.
_CONTENT_ELIDED = "<elided>"

# Constant used for the value of 'gen_ai.operation.name".
_GENERATE_CONTENT_OP_NAME = "generate_content"


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
        return value.model_dump()
    return json.loads(json.dumps(value))


def _add_request_options_to_span(
    span, config: Optional[GenerateContentConfigOrDict], allow_list: AllowList
):
    if config is None:
        return
    span_context = span.get_span_context()
    if not span_context.trace_flags.sampled:
        # Avoid potentially costly traversal of config
        # options if the span will be dropped, anyway.
        return
    # Automatically derive attributes from the contents of the
    # config object. This ensures that all relevant parameters
    # are captured in the telemetry data (except for those
    # that are excluded via "exclude_keys"). Dynamic attributes (those
    # starting with "gcp.gen_ai." instead of simply "gen_ai.request.")
    # are filtered with the "allow_list" before inclusion in the span.
    attributes = flatten_dict(
        _to_dict(config),
        # A custom prefix is used, because the names/structure of the
        # configuration is likely to be specific to Google Gen AI SDK.
        key_prefix=CUSTOM_LLM_REQUEST_PREFIX,
        exclude_keys=[
            # System instruction can be overly long for a span attribute.
            # Additionally, it is recorded as an event (log), instead.
            "gcp.gen_ai.request.system_instruction",
        ],
        # Although a custom prefix is used by default, some of the attributes
        # are captured in common, standard, Semantic Conventions. For the
        # well-known properties whose values align with Semantic Conventions,
        # we ensure that the key name matches the standard SemConv name.
        rename_keys={
            # TODO: add more entries here as more semantic conventions are
            # generalized to cover more of the available config options.
            "gcp.gen_ai.request.temperature": gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE,
            "gcp.gen_ai.request.top_k": gen_ai_attributes.GEN_AI_REQUEST_TOP_K,
            "gcp.gen_ai.request.top_p": gen_ai_attributes.GEN_AI_REQUEST_TOP_P,
            "gcp.gen_ai.request.candidate_count": gen_ai_attributes.GEN_AI_REQUEST_CHOICE_COUNT,
            "gcp.gen_ai.request.max_output_tokens": gen_ai_attributes.GEN_AI_REQUEST_MAX_TOKENS,
            "gcp.gen_ai.request.stop_sequences": gen_ai_attributes.GEN_AI_REQUEST_STOP_SEQUENCES,
            "gcp.gen_ai.request.frequency_penalty": gen_ai_attributes.GEN_AI_REQUEST_FREQUENCY_PENALTY,
            "gcp.gen_ai.request.presence_penalty": gen_ai_attributes.GEN_AI_REQUEST_PRESENCE_PENALTY,
            "gcp.gen_ai.request.seed": gen_ai_attributes.GEN_AI_REQUEST_SEED,
        },
    )
    for key, value in attributes.items():
        if key.startswith(
            CUSTOM_LLM_REQUEST_PREFIX
        ) and not allow_list.allowed(key):
            # The allowlist is used to control inclusion of the dynamic keys.
            continue
        span.set_attribute(key, value)


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


class _GenerateContentInstrumentationHelper:
    def __init__(
        self,
        models_object: Union[Models, AsyncModels],
        otel_wrapper: OTelWrapper,
        model: str,
        generate_content_config_key_allowlist: Optional[AllowList] = None,
    ):
        self._start_time = time.time_ns()
        self._otel_wrapper = otel_wrapper
        self._genai_system = _determine_genai_system(models_object)
        self._genai_request_model = model
        self._finish_reasons_set = set()
        self._error_type = None
        self._input_tokens = 0
        self._output_tokens = 0
        self._content_recording_enabled = is_content_recording_enabled()
        self._response_index = 0
        self._candidate_index = 0
        self._generate_content_config_key_allowlist = (
            generate_content_config_key_allowlist or AllowList()
        )

    def start_span_as_current_span(
        self, model_name, function_name, end_on_exit=True
    ):
        return self._otel_wrapper.start_as_current_span(
            f"{_GENERATE_CONTENT_OP_NAME} {model_name}",
            start_time=self._start_time,
            attributes={
                code_attributes.CODE_FUNCTION_NAME: function_name,
                gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
                gen_ai_attributes.GEN_AI_REQUEST_MODEL: self._genai_request_model,
                gen_ai_attributes.GEN_AI_OPERATION_NAME: _GENERATE_CONTENT_OP_NAME,
            },
            end_on_exit=end_on_exit,
        )

    def process_request(
        self,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict],
    ):
        span = trace.get_current_span()
        _add_request_options_to_span(
            span, config, self._generate_content_config_key_allowlist
        )
        self._maybe_log_system_instruction(config=config)
        self._maybe_log_user_prompt(contents)

    def process_response(self, response: GenerateContentResponse):
        # TODO: Determine if there are other response properties that
        # need to be reflected back into the span attributes.
        #
        # See also: TODOS.md.
        self._maybe_update_token_counts(response)
        self._maybe_update_error_type(response)
        self._maybe_log_response(response)
        self._response_index += 1

    def process_error(self, e: Exception):
        self._error_type = str(e.__class__.__name__)

    def finalize_processing(self):
        span = trace.get_current_span()
        span.set_attribute(
            gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS, self._input_tokens
        )
        span.set_attribute(
            gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS, self._output_tokens
        )
        span.set_attribute(
            gen_ai_attributes.GEN_AI_RESPONSE_FINISH_REASONS,
            sorted(self._finish_reasons_set),
        )
        self._record_token_usage_metric()
        self._record_duration_metric()

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

    def _maybe_log_system_instruction(
        self, config: Optional[GenerateContentConfigOrDict] = None
    ):
        system_instruction = None
        if config is not None:
            if isinstance(config, dict):
                system_instruction = config.get("system_instruction")
            else:
                system_instruction = config.system_instruction
        if not system_instruction:
            return
        attributes = {
            gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
        }
        # TODO: determine if "role" should be reported here or not. It is unclear
        # since the caller does not supply a "role" and since this comes through
        # a property named "system_instruction" which would seem to align with
        # the default "role" that is allowed to be omitted by default.
        #
        # See also: "TODOS.md"
        body = {}
        if self._content_recording_enabled:
            body["content"] = _to_dict(system_instruction)
        else:
            body["content"] = _CONTENT_ELIDED
        self._otel_wrapper.log_system_prompt(
            attributes=attributes,
            body=body,
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
        helper = _GenerateContentInstrumentationHelper(
            self,
            otel_wrapper,
            model,
            generate_content_config_key_allowlist=generate_content_config_key_allowlist,
        )
        with helper.start_span_as_current_span(
            model, "google.genai.Models.generate_content"
        ):
            helper.process_request(contents, config)
            try:
                response = wrapped_func(
                    self,
                    model=model,
                    contents=contents,
                    config=config,
                    **kwargs,
                )
                helper.process_response(response)
                return response
            except Exception as error:
                helper.process_error(error)
                raise
            finally:
                helper.finalize_processing()

    return instrumented_generate_content


def _create_instrumented_generate_content_stream(
    snapshot: _MethodsSnapshot,
    otel_wrapper: OTelWrapper,
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
        helper = _GenerateContentInstrumentationHelper(
            self,
            otel_wrapper,
            model,
            generate_content_config_key_allowlist=generate_content_config_key_allowlist,
        )
        with helper.start_span_as_current_span(
            model, "google.genai.Models.generate_content_stream"
        ):
            helper.process_request(contents, config)
            try:
                for response in wrapped_func(
                    self,
                    model=model,
                    contents=contents,
                    config=config,
                    **kwargs,
                ):
                    helper.process_response(response)
                    yield response
            except Exception as error:
                helper.process_error(error)
                raise
            finally:
                helper.finalize_processing()

    return instrumented_generate_content_stream


def _create_instrumented_async_generate_content(
    snapshot: _MethodsSnapshot,
    otel_wrapper: OTelWrapper,
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
            generate_content_config_key_allowlist=generate_content_config_key_allowlist,
        )
        with helper.start_span_as_current_span(
            model, "google.genai.AsyncModels.generate_content"
        ):
            helper.process_request(contents, config)
            try:
                response = await wrapped_func(
                    self,
                    model=model,
                    contents=contents,
                    config=config,
                    **kwargs,
                )
                helper.process_response(response)
                return response
            except Exception as error:
                helper.process_error(error)
                raise
            finally:
                helper.finalize_processing()

    return instrumented_generate_content


# Disabling type checking because this is not yet implemented and tested fully.
def _create_instrumented_async_generate_content_stream(  # type: ignore
    snapshot: _MethodsSnapshot,
    otel_wrapper: OTelWrapper,
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
            generate_content_config_key_allowlist=generate_content_config_key_allowlist,
        )
        with helper.start_span_as_current_span(
            model,
            "google.genai.AsyncModels.generate_content_stream",
            end_on_exit=False,
        ) as span:
            helper.process_request(contents, config)
        try:
            response_async_generator = await wrapped_func(
                self,
                model=model,
                contents=contents,
                config=config,
                **kwargs,
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            helper.process_error(error)
            helper.finalize_processing()
            with trace.use_span(span, end_on_exit=True):
                raise

        async def _response_async_generator_wrapper():
            with trace.use_span(span, end_on_exit=True):
                try:
                    async for response in response_async_generator:
                        helper.process_response(response)
                        yield response
                except Exception as error:
                    helper.process_error(error)
                    raise
                finally:
                    helper.finalize_processing()

        return _response_async_generator_wrapper()

    return instrumented_generate_content_stream


def uninstrument_generate_content(snapshot: object):
    assert isinstance(snapshot, _MethodsSnapshot)
    snapshot.restore()


def instrument_generate_content(
    otel_wrapper: OTelWrapper,
    generate_content_config_key_allowlist: Optional[AllowList] = None,
) -> object:
    snapshot = _MethodsSnapshot()
    Models.generate_content = _create_instrumented_generate_content(
        snapshot,
        otel_wrapper,
        generate_content_config_key_allowlist=generate_content_config_key_allowlist,
    )
    Models.generate_content_stream = _create_instrumented_generate_content_stream(
        snapshot,
        otel_wrapper,
        generate_content_config_key_allowlist=generate_content_config_key_allowlist,
    )
    AsyncModels.generate_content = _create_instrumented_async_generate_content(
        snapshot,
        otel_wrapper,
        generate_content_config_key_allowlist=generate_content_config_key_allowlist,
    )
    AsyncModels.generate_content_stream = _create_instrumented_async_generate_content_stream(
        snapshot,
        otel_wrapper,
        generate_content_config_key_allowlist=generate_content_config_key_allowlist,
    )
    return snapshot
