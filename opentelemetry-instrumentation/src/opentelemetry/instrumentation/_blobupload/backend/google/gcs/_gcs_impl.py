import io
import uuid
import logging

from typing import Optional, TypeAlias

from opentelemetry.instrumentation._blobupload.api import Blob
from opentelemetry.instrumentation._blobupload.api import BlobUploader
from opentelemetry.instrumentation._blobupload.utils import SimpleBlobUploader
from opentelemetry.instrumentation._blobupload.utils import blob_uploader_from_simple_blob_uploader
from opentelemetry.instrumentation._blobupload.backend.google.gcs import _gcs_client_wrapper

_logger = logging.getLogger(__name__)

GcsClient: TypeAlias = _gcs_client_wrapper.GcsClientType


def _path_for_span(trace_id, span_id):
    if not trace_id or not span_id:
        return ''
    return 'traces/{}/spans/{}'.format(trace_id, span_id)


def _path_for_event(trace_id, span_id, event_name):
    if not event_name:
        return ''
    span_path = _path_for_span(trace_id, span_id)
    if not span_path:
        return ''
    return '{}/events/{}'.format(span_path, event_name)


def _path_for_span_event(trace_id, span_id, event_index):
    if event_index is None:
        return ''
    span_path = _path_for_span(trace_id, span_id)
    if not span_path:
        return ''
    return '{}/events/{}'.format(span_path, event_index)


def _path_segment_from_labels(labels):
    """Returns a path segment based on blob label metadata.
    
    This aims to return paths like:

       'traces/12345/spans/56789'
       'traces/12345/spans/56789/events/0'
       'traces/12345/spans/56789/events/some.event.name'

    ...depending on the particular type of signal source.

    """
    signal_type = labels.get('otel_type')
    if not signal_type or signal_type not in ['span', 'event', 'span_event']:
        return ''
    trace_id = labels.get('trace_id')
    span_id = labels.get('span_id')
    event_name = labels.get('event_name')
    event_index = labels.get('event_index')
    if signal_type == 'span':
        return _path_for_span(trace_id, span_id)
    elif signal_type == 'event':
        return _path_for_event(trace_id, span_id, event_name)
    elif signal_type == 'span_event':
        return _path_for_span_event(trace_id, span_id, event_index)


class _SimpleGcsBlobUploader(SimpleBlobUploader):

    def __init__(self, prefix: str, client:Optional[GcsClient]=None):
        if not prefix:
            raise ValueError('Must supply a non-empty prefix.')
        if not prefix.startswith('gs://'):
            raise ValueError('Invalid prefix; must start with "gs://"; found: "{}".'.format(prefix))
        if not prefix.endswith('/'):
            prefix = '{}/'.format(prefix)
        self._prefix = prefix
        self._client = client or _gcs_client_wrapper.create_gcs_client()

    def generate_destination_uri(self, blob: Blob) -> str:
        origin_path = _path_segment_from_labels(blob.labels)
        if origin_path and not origin_path.endswith('/'):
            origin_path = '{}/'.format(origin_path)
        upload_id = uuid.uuid4().hex
        return '{}{}uploads/{}'.format(self._prefix, origin_path, upload_id)

    def upload_sync(self, uri: str, blob: Blob):
        _logger.debug('Uploading blob: size: {} -> "{}"'.format(len(blob.raw_bytes), uri))
        gcs_blob = _gcs_client_wrapper.blob_from_uri(uri, client=self._client)
        gcs_blob.upload_from_file(
            io.BytesIO(blob.raw_bytes),
            content_type=blob.content_type)
        metadata = gcs_blob.metadata or {}
        metadata.update(blob.labels)
        gcs_blob.metadata = metadata



class GcsBlobUploader(BlobUploader):

    def __init__(self, prefix: str, client:Optional[GcsClient]=None):
        if not _gcs_client_wrapper.is_gcs_initialized():
            raise NotImplementedError("GcsBlobUploader implementation unavailable without 'google-cloud-storage' optional dependency.")
        simple_uploader = _SimpleGcsBlobUploader(prefix, client)
        self._delegate = blob_uploader_from_simple_blob_uploader(simple_uploader)

    def upload_async(self, blob: Blob) -> str:
        return self._delegate.upload_async(blob)
