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

import logging
from os import environ

from opentelemetry.util.genai.completion_hook import (
    CompletionHook,
    _NoOpCompletionHook,
)
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH,
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT,
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_MAX_QUEUE_SIZE,
)

_logger = logging.getLogger(__name__)


def upload_completion_hook() -> CompletionHook:
    base_path = environ.get(OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH)
    if not base_path:
        _logger.warning(
            "%s is required but not set, using no-op instead",
            OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH,
        )
        return _NoOpCompletionHook()

    # If fsspec is not installed the hook will be a no-op.
    try:
        # pylint: disable=import-outside-toplevel
        from opentelemetry.util.genai._upload.completion_hook import (  # noqa: PLC0415
            _DEFAULT_FORMAT,
            _DEFAULT_MAX_QUEUE_SIZE,
            _FORMATS,
            UploadCompletionHook,
        )
    except ImportError:
        return _NoOpCompletionHook()

    environ_max_queue_size = environ.get(
        OTEL_INSTRUMENTATION_GENAI_UPLOAD_MAX_QUEUE_SIZE,
        _DEFAULT_MAX_QUEUE_SIZE,
    )
    try:
        environ_max_queue_size = int(environ_max_queue_size)
    except ValueError:
        _logger.warning(
            "%s is not a valid integer for %s. Defaulting to %s.",
            environ_max_queue_size,
            OTEL_INSTRUMENTATION_GENAI_UPLOAD_MAX_QUEUE_SIZE,
            _DEFAULT_MAX_QUEUE_SIZE,
        )
        environ_max_queue_size = _DEFAULT_MAX_QUEUE_SIZE

    environ_format = environ.get(
        OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT, _DEFAULT_FORMAT
    ).lower()

    if environ_format not in _FORMATS:
        _logger.warning(
            "%s is not a valid option for %s, should be be one of %s. Defaulting to %s.",
            environ_format,
            OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT,
            _FORMATS,
            _DEFAULT_FORMAT,
        )
        environ_format = _DEFAULT_FORMAT

    return UploadCompletionHook(
        base_path=base_path,
        max_queue_size=environ_max_queue_size,
        upload_format=environ_format,
    )
