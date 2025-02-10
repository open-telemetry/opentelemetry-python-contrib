import os

_CONTENT_RECORDING_ENV_VAR = 'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'


def is_content_recording_enabled():
    return os.getenv(
        _CONTENT_RECORDING_ENV_VAR,
        'false'
    ).lower() in ['1', 'true', 'yes', 'on']
