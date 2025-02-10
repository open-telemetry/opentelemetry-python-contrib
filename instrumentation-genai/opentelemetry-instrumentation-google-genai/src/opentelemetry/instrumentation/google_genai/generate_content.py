import time
import os
import functools


from google.genai.models import Models, AsyncModels
from google.genai.types import (
    ContentListUnion,
    ContentListUnionDict,
    GenerateContentConfigOrDict,
    GenerateContentResponse,
)
from .flags import is_content_recording_enabled
from .otel_wrapper import OTelWrapper

from opentelemetry import trace
from opentelemetry.semconv.attributes import error_attributes
from opentelemetry.semconv._incubating import gen_ai_attributes

_original_generate_content = Models.generate_content
_original_generate_content_stream = Models.generate_content_stream
_original_async_generate_content = AsyncModels.generate_content
_original_async_generate_content_stream = AsyncModels.generate_content_stream


def _get_vertexai_system_name():
    return gen_ai_attributes.GenaiSystemValues.VERTEX_AI


def _get_gemini_system_name():
    return gen_ai_attributes.GenaiSystemValues.GEMINI


def _guess_genai_system_from_env():
    if os.environ.get('GOOGLE_GENAI_USE_VERTEXAI', '0').lower() in [
          'true',
          '1',
      ]:
      return _get_vertexai_system_name()
    return _get_gemini_system_name()



def _determine_genai_system(models_object: Union[Models, AsyncModels]):
    client = getattr(models_object, '_api_client')
    if not client:
        return _guess_genai_system_from_env()
    vertexai_attr = getattr(client, 'vertexai')
    if vertexai_attr is None:
        return _guess_genai_system_from_env()
    if vertexai_attr:
        return _get_vertexai_system_name()
    return _get_gemini_system_name()



def _get_config_property(
    config: Optional[GenerateContentConfigOrDict],
    path: str):
    if config is None:
        return None
    path_segments = path.split('.')
    current_context = config
    for path_segment in path_segments:
        if current_context is None
            return None
        if isdict(current_context):
            current_context = current_context.get(path_segment)
        else:
            current_context = getattr(current_context, path_segment)
    return current_context


def _get_temperature(config: Optional[GenerateContentConfigOrDict]):
    return _get_config_property(config, 'temperature')


def _get_top_k(config: Optional[GenerateContentConfigOrDict]):
    return _get_config_property(config, 'top_k')


def _get_top_p(config: Optional[GenerateContentConfigOrDict]):
    return _get_config_property(config, 'top_p')


_SPAN_ATTRIBUTE_TO_CONFIG_EXTRACTOR = {
    gen_ai_attributes.GEN_AI_REQUEST_TEMPERATURE: _get_temperature,
    gen_ai_attributes.GEN_AI_REQUEST_TOP_K: _get_top_k,
    gen_ai_attributes.GEN_AI_REQUEST_TOP_P: _get_top_p,
}


class _GenerateContentInstrumentationHelper:

    def __init__(
        self,
        otel_wrapper: OTelWrapper,
        models_object: Union[Models, AsyncModels],
        model: str):
        self._start_time = time.time_ns()
        self._otel_wrapper = otel_wrapper
        self._genai_system = _determine_genai_system(models_object)
        self._genai_request_model = model
        self._finish_reasons_set = set()
        self._error_type = None
        self._input_tokens = 0
        self._output_tokens = 0
        self._content_recording_enabled = is_content_recording_enabled()

    def start_span_as_current_span(self):
        return self._otel_wrapper.tracer.start_span_as_current_span(
            'google.genai.GenerateContent',
            start_time=self._start_time,
            attributes={
                gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
                gen_ai_attributes.GEN_AI_REQUEST_MODEL: self._genai_request_model,
                gen_ai_attributes.GEN_AI_OPERATION_NAME: 'GenerateContent',
            }
        )

    def process_request(
        self,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict]):
        span = trace.get_current_span()
        for attribute_key, extractor in _SPAN_ATTRIBUTE_TO_CONFIG_EXTRACTOR:
            attribute_value = extractor(config)
            if attribute_value is not None:
                span.set_attribute(attribute_key, attribute_value)
        self._maybe_log_system_instruction(config)
        self._maybe_log_user_prompt(contents)
        

    def process_response(self, response: GenerateContentResponse):
        pass

    def process_error(self, e: Exception):
        self._error_type = str(e.__class__.__name__)

    def finalize_processing(self):
        span = trace.get_current_span()
        span.set_attribute(gen_ai_attributes.GEN_AI_USAGE_INPUT_TOKENS, self._input_tokens)
        span.set_attribute(gen_ai_attributes.GEN_AI_USAGE_OUTPUT_TOKENS, self._output_tokens)
        span.set_attribute(gen_ai_attributes.GEN_AI_RESPONSE_FINISH_REASONS, sorted(list(self._finish_reasons_set)))
        self._record_token_usage_metric()
        self._record_duration_metric()

    def _maybe_log_system_instruction(config: Optional[GenerateContentConfigOrDict]):
        if not self._content_recording_enabled:
            return
        pass
    
    def _maybe_log_user_prompt(contents: Union[ContentListUnion, ContentListUnionDict]):
        if not self._content_recording_enabled:
            return
        pass

    def _record_token_usage_metric(self):
        self._otel_wrapper.token_usage_metric.record(
            self._input_tokens,
            attributes={
                gen_ai_attributes.GEN_AI_TOKEN_TYPE: gen_ai_attributes.GenAiTokenTypeValues.INPUT,
                gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
                gen_ai_attributes.GEN_AI_REQUEST_MODEL: self._genai_request_model,
                gen_ai_attributes.GEN_AI_OPERATION_NAME: 'GenerateContent',
            }
        )
        self._otel_wrapper.token_usage_metric.record(
            self._output_tokens,
            attributes={
                gen_ai_attributes.GEN_AI_TOKEN_TYPE: gen_ai_attributes.GenAiTokenTypeValues.OUTPPUT,
                gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
                gen_ai_attributes.GEN_AI_REQUEST_MODEL: self._genai_request_model,
                gen_ai_attributes.GEN_AI_OPERATION_NAME: 'GenerateContent',
            }
        )
    
    def _record_duration_metric(self):
        attributes = {
            gen_ai_attributes.GEN_AI_SYSTEM: self._genai_system,
            gen_ai_attributes.GEN_AI_REQUEST_MODEL: self._genai_request_model,
            gen_ai_attributes.GEN_AI_OPERATION_NAME: 'GenerateContent',
        }
        if self._error_type is not None:
            attributes[error_attributes.ERROR_TYPE] = self._error_type
        duration_nanos = time.time_ns() - self._start_time
        duration_seconds = duration_nanos / 1e9
        self._otel_wrapper.operation_duration_metric.record(
            duration_seconds,
            attributes=attributes,
        )



def _create_instrumented_generate_content(otel_wrapper: OTelWrapper):
    @functools.wraps(_original_generate_content)
    def instrumented_generate_content(
        self: Models,
        *,
        model: str,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict]) -> GenerateContentResponse:
        helper = _GenerateContentInstrumentationHelper(self, otel_wrapper, model)
        with helper.start_span_as_current_span():
            helper.process_request(contents, config)
            try:
                response = _original_generate_content(self, model=model, contents=contents, config=config)
                helper.process_response(response)
                return response
            except Exception as e:
                helper.process_error(e)
                raise
            finally:
                helper.finalize_processing()
    return instrument_generate_content


def _create_instrumented_generate_content_stream(otel_wrapper: OTelWrapper):
    @functools.wraps(_original_generate_content_stream)
    def instrumented_generate_content_stream(
        self: Models,
        *,
        model: str,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict]) -> Iterator[GenerateContentResponse]:
        helper = _GenerateContentInstrumentationHelper(self, otel_wrapper, model)
        with helper.start_span_as_current_span():
            helper.process_request(contents, config)
            try:
                for response in _original_generate_content_stream(self, model=model, contents=contents, config=config):
                    helper.process_response(response)
                    yield response
            except Exception as e:
                helper.process_error(e)
                raise
            finally:
                helper.finalize_processing()
    return instrument_generate_content


def _create_instrumented_async_generate_content(otel_wrapper: OTelWrapper):
    @functools.wraps(_original_async_generate_content)
    async def instrumented_generate_content(
        self: AsyncModels,
        *,
        model: str,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict]) -> GenerateContentResponse
        helper = _GenerateContentInstrumentationHelper(self, otel_wrapper, model)
        with helper.start_span_as_current_span():
            helper.process_request(contents, config)
            try:
                response = await _original_async_generate_content(self, model=model, contents=contents, config=config)
                helper.process_response(response)
                return response
            except Exception as e:
                helper.process_error(e)
                raise
            finally:
                helper.finalize_processing()
    return instrument_generate_content


def _create_instrumented_async_generate_content_stream(otel_wrapper: OTelWrapper):
    @functools.wraps(_original_async_generate_content_stream)
    async def instrumented_generate_content_stream(
        self: AsyncModels,
        *,
        model: str,
        contents: Union[ContentListUnion, ContentListUnionDict],
        config: Optional[GenerateContentConfigOrDict]) -> Awaitable[AsyncIterator[types.GenerateContentResponse]]:
        helper = _GenerateContentInstrumentationHelper(self, otel_wrapper, model)
        with helper.start_span_as_current_span():
            helper.process_request(contents, config)
            try:
                async for response in _original_async_generate_content_stream(self, model=model, contents=contents, config=config)
                    helper.process_response(response)
                    yield response
            except Exception as e:
                helper.process_error(e)
                raise
            finally:
                helper.finalize_processing()
    return instrument_generate_content


def uninstrument_generate_content():
    Models.generate_content = _original_generate_content
    Models.generate_content_stream = _original_generate_content_stream
    AsyncModels.generate_content = _original_async_generate_content
    AsyncModels.generate_content_stream = _original_async_generate_content_stream


def instrument_generate_content(otel_wrapper: OTelWrapper):
    Models.generate_content = _create_instrumented_generate_content(otel_wrapper)
    Models.generate_content_stream = _create_instrumented_generate_content_stream(otel_wrapper)
    AsyncModels.generate_content = _create_instrumented_async_generate_content(otel_wrapper)
    AsyncModels.generate_content_stream = _create_instrumented_async_generate_content_stream(otel_wrapper)