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

"""Exposes API methods to callers from the package name."""

from opentelemetry.instrumentation._blobupload.api.blob import Blob
from opentelemetry.instrumentation._blobupload.api.blob_uploader import (
    BlobUploader,
)
from opentelemetry.instrumentation._blobupload.api.constants import (
    NOT_UPLOADED,
)
from opentelemetry.instrumentation._blobupload.api.content_type import (
    detect_content_type,
)
from opentelemetry.instrumentation._blobupload.api.labels import (
    generate_labels_for_event,
    generate_labels_for_span,
    generate_labels_for_span_event,
)
from opentelemetry.instrumentation._blobupload.api.provider import (
    BlobUploaderProvider,
    get_blob_uploader,
    set_blob_uploader_provider,
)

__all__ = [
    "Blob",
    "BlobUploader",
    "NOT_UPLOADED",
    "detect_content_type",
    "generate_labels_for_event",
    "generate_labels_for_span",
    "generate_labels_for_span_event",
    "BlobUploaderProvider",
    "get_blob_uploader",
    "set_blob_uploader_provider",
]
