from concurrent.futures import Executor, ProcessPoolExecutor

from opentelemetry.instrumentation._blobupload.api import Blob
from opentelemetry.instrumentation._blobupload.api import BlobUploader
from opentelemetry.instrumentation._blobupload.api import detect_content_type
from opentelemetry.instrumentation._blobupload.utils.simple_blob_uploader import SimpleBlobUploader


def _with_content_type(blob: Blob) -> Blob:
    if blob.content_type is not None:
        return blob
    content_type = detect_content_type(blob.raw_bytes)
    return Blob(blob.raw_bytes, content_type=content_type, labels=blob.labels)


def _UploadAction(object):

    def __init__(self, simple_uploader, uri, blob):
        self._simple_uploader = simple_uploader
        self._uri = uri
        self._blob = blob
    
    def __call__(self):
        self._simple_uploader.upload_sync(self._uri, self._blob)


def _create_default_executor():
    return ProcessPoolExecutor()


class _SimpleBlobUploaderAdaptor(BlobUploader):

    def __init__(self, simple_uploader, executor=None):
        self._simple_uploader = simple_uploader
        self._executor = executor or _create_default_executor()

    def upload_async(self, blob: Blob) -> str:
        full_blob = _with_content_type(blob)
        uri = self._simple_uploader.generate_destination_uri(full_blob)
        self._do_in_background(_UploadAction(self._simple_uploader, uri, full_blob))
        return uri

    def _do_in_background(self, action):



def blob_uploader_from_simple_blob_uploader(simple_uploader: SimpleBlobUploader) -> BlobUploader:
    return _SimpleBlobUploaderAdaptor(simple_uploader)

