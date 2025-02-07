import functools


from google.genai.models import Models, AsyncModels
from .otel_wrapper import OTelWrapper

_original_generate_content = Models.generate_content
_original_generate_content_stream = Models.generate_content_stream
_original_async_generate_content = AsyncModels.generate_content
_original_async_generate_content_stream = AsyncModels.generate_content_stream


def _create_instrumented_generate_content(otel_wrapper: OTelWrapper):
    @functools.wraps(_original_generate_content)
    def instrumented_generate_content():
        pass
    return instrument_generate_content


def _create_instrumented_generate_content_stream(otel_wrapper: OTelWrapper):
    @functools.wraps(_original_generate_content_stream)
    def instrumented_generate_content_stream():
        pass
    return instrument_generate_content


def _create_instrumented_async_generate_content(otel_wrapper: OTelWrapper):
    @functools.wraps(_original_async_generate_content)
    async def instrumented_generate_content():
        pass
    return instrument_generate_content


def _create_instrumented_async_generate_content_stream(otel_wrapper: OTelWrapper):
    @functools.wraps(_original_async_generate_content_stream)
    async def instrumented_generate_content_stream():
        pass
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