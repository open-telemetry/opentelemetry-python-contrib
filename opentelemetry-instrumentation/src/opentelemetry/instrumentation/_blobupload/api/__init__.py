"""Exposes API methods to callers from the package name."""

from opentelemetry.instrumentation._blobupload.api.constants import NOT_UPLOADED
from opentelemetry.instrumentation._blobupload.api.blob import Blob
from opentelemetry.instrumentation._blobupload.api.blob_uploader import BlobUploader
from opentelemetry.instrumentation._blobupload.api.content_type import detect_content_type
from opentelemetry.instrumentation._blobupload.api.labels import (
    generate_labels_for_span,
    generate_labels_for_event,
    generate_labels_for_span_event
)
from opentelemetry.instrumentation._blobupload.api.provider import (
    BlobUploaderProvider,
    set_blob_uploader_provider,
    get_glob_uploader
)
