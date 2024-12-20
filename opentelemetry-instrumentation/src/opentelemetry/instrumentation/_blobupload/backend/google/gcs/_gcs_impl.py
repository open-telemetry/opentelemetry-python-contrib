import io
import uuid

from google.cloud.storage import Client as GcsClient
from google.cloud.storage import Blob as GcsBlob

from opentelemetry.instrumentation._blobupload.api import Blob
from opentelemetry.instrumentation._blobupload.api import BlobUploader
from opentelemetry.instrumentation._blobupload.utils import SimpleBlobUploader
from opentelemetry.instrumentation._blobupload.utils import blob_uploader_from_simple_blob_uploader


def _path_segment_from_labels(labels):
    """Returns a path segment based on blob label metadata.
    
    This aims to return paths like:

       'traces/12345/spans/56789'
       'traces/12345/spans/56789/events/0'
       'traces/12345/spans/56789/events/some.event.name'

    ...depending on the particular type of signal source.

    """
    segments = []
    target_segments = [
        ('traces', 'trace_id', 'unknown'),
        ('spans', 'span_id', 'unknown'),
        ('events', 'event_index', None),
    ]
    for segment_prefix, label_key, default_val in target_segments:
        label_value = labels.get(label_key) or default_val
        if label_value:
            segments.append(segment_prefix)
            segments.append(label_value)
    if ((labels.get('otel_type') in ['event', 'span_event']) and 
        ('events' not in segments)):
        event_name = labels.get('event_name') or 'unknown'
        segments.append('events')
        segments.append(event_name)
    return '/'.join(segments)



class _SimpleGcsBlobUploader(SimpleBlobUploader):

    def __init__(self, prefix: str, client:Optional[GcsClient]=None):
        if not prefix:
            raise ValueError('Must supply a non-empty prefix.')
        if not prefix.startswith('gs://'):
            raise ValueError('Invalid prefix; must start with "gs://"; found: "{}".'.format(prefix))
        if not prefix.endswith('/'):
            prefix = '{}/'.format(prefix)
        self._prefix = prefix
        self._client = client or GcsClient()

    def generate_destination_uri(self, blob: Blob) -> str:
        origin_path = _path_segment_from_labels(blob.labels)
        upload_id = uuid.uuid4().hex
        return '{}{}/uploads/{}'.format(self._prefix, origin_path, upload_id)

    def upload_sync(self, uri: str, blob: Blob):
        gcs_blob = GcsBlob.from_string(uri, client=self._client)
        gcs_blob.upload_from_file(
            io.BytesIO(blob.raw_bytes),
            content_type=blob.content_type)
        metadata = gcs_blob.metadata or {}
        metadata.update(blob.labels)
        gcs_blob.metadata = metadata


class GcsBlobUploader(BlobUploader):

    def __init__(self, prefix: str, client:Optional[GcsClient]=None):
        simple_uploader = _SimpleGcsBlobUploader(prefix, client)
        self._delegate = blob_uploader_from_simple_blob_uploader(simple_uploader)

    def upload_async(self, blob: Blob) -> str:
        return self._delegate.upload_async(blob)
