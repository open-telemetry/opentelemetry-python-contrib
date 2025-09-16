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

"""This module defines the generic hooks for GenAI content uploading

The hooks are specified as part of semconv in `Uploading content to external storage
<https://github.com/open-telemetry/semantic-conventions/blob/v1.37.0/docs/gen-ai/gen-ai-spans.md#uploading-content-to-external-storage>`__.

This module defines the `UploadHook` type that custom implementations should implement, and a
`load_upload_hook` function to load it from an entry point.
"""

from __future__ import annotations

import logging
from os import environ
from typing import Any, Protocol, cast, runtime_checkable

from opentelemetry._logs import LogRecord
from opentelemetry.trace import Span
from opentelemetry.util._importlib_metadata import (
    entry_points,  # pyright: ignore[reportUnknownVariableType]
)
from opentelemetry.util.genai import types
from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK,
)

_logger = logging.getLogger(__name__)


@runtime_checkable
class UploadHook(Protocol):
    """A hook to upload GenAI content to an external storage.

    This is the interface for a hook that can be
    used to upload GenAI content to an external storage. The hook is a
    callable that takes the inputs, outputs, and system instruction of a
    GenAI interaction, as well as the span and log record associated with
    it.

    The hook can be used to upload the content to any external storage,
    such as a database, a file system, or a cloud storage service.

    The span and log_record arguments should be provided based on the content capturing mode
    :func:`~opentelemetry.util.genai.utils.get_content_capturing_mode`.

    Args:
        inputs: The inputs of the GenAI interaction.
        outputs: The outputs of the GenAI interaction.
        system_instruction: The system instruction of the GenAI
            interaction.
        span: The span associated with the GenAI interaction.
        log_record: The event log associated with the GenAI
            interaction.
    """

    def upload(
        self,
        *,
        inputs: list[types.InputMessage],
        outputs: list[types.OutputMessage],
        system_instruction: list[types.MessagePart],
        span: Span | None = None,
        log_record: LogRecord | None = None,
    ) -> None: ...


class _NoOpUploadHook(UploadHook):
    def upload(self, **kwargs: Any) -> None:
        return None


def load_upload_hook() -> UploadHook:
    """Load the upload hook from entry point or return a noop implementation

    This function loads an upload hook from the entry point group
    ``opentelemetry_genai_upload_hook`` with name coming from
    :envvar:`OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK`. If one can't be found, returns a no-op
    implementation.
    """
    hook_name = environ.get(OTEL_INSTRUMENTATION_GENAI_UPLOAD_HOOK, None)
    if not hook_name:
        return _NoOpUploadHook()

    for entry_point in entry_points(group="opentelemetry_genai_upload_hook"):  # pyright: ignore[reportUnknownVariableType]
        name = cast(str, entry_point.name)  # pyright: ignore[reportUnknownMemberType]
        try:
            if hook_name != name:
                continue

            hook = entry_point.load()()  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            if not isinstance(hook, UploadHook):
                _logger.debug("%s is not a valid UploadHook. Using noop", name)
                continue

            _logger.debug("Using UploadHook %s", name)
            return hook

        except Exception:  # pylint: disable=broad-except
            _logger.exception(
                "UploadHook %s configuration failed. Using noop", name
            )

    return _NoOpUploadHook()


__all__ = ["UploadHook", "load_upload_hook"]
