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

from os import environ

from opentelemetry.util.genai.environment_variables import (
    OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH,
)
from opentelemetry.util.genai.upload_hook import UploadHook, _NoOpUploadHook


def fsspec_upload_hook() -> UploadHook:
    # If fsspec is not installed the hook will be a no-op.
    try:
        # pylint: disable=import-outside-toplevel
        from opentelemetry.util.genai._fsspec_upload.fsspec_hook import (
            FsspecUploader,
            FsspecUploadHook,
        )
    except ImportError:
        return _NoOpUploadHook()

    base_path = environ.get(OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH)
    if not base_path:
        return _NoOpUploadHook()

    return FsspecUploadHook(
        uploader=FsspecUploader(),
        base_path=base_path,
    )
