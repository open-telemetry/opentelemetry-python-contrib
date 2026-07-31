# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from os import environ
from typing import Union

from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT,
)
from opentelemetry.util.genai.types import ContentCapturingMode
from opentelemetry.util.genai.utils import get_content_capturing_mode


def is_content_recording_enabled(
    experimental_sem_convs_enabled: bool,
) -> Union[bool, ContentCapturingMode]:
    if experimental_sem_convs_enabled:
        return get_content_capturing_mode()
    return (
        environ.get(
            OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false"
        ).lower()
        == "true"
    )
