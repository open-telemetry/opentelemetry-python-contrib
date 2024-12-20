import atexit

from concurrent.futures import Executor, ProcessPoolExecutor

from opentelemetry.instrumentation._blobupload.api import Blob
from opentelemetry.instrumentation._blobupload.api import BlobUploader
from opentelemetry.instrumentation._blobupload.api import detect_content_type
from opentelemetry.instrumentation._blobupload.utils.simple_blob_uploader import SimpleBlobUploader


def _with_content_type(blob: Blob) -> Blob:
    """Returns a variant of the Blob with the content type auto-detected if needed."""
    if blob.content_type is not None:
        return blob
    content_type = detect_content_type(blob.raw_bytes)
    return Blob(blob.raw_bytes, content_type=content_type, labels=blob.labels)


def _UploadAction(object):
    """Represents the work to be done in the background to upload a blob."""

    def __init__(self, simple_uploader, uri, blob):
        self._simple_uploader = simple_uploader
        self._uri = uri
        self._blob = blob
    
    def __call__(self):
        self._simple_uploader.upload_sync(self._uri, self._blob)


def _create_default_executor_no_cleanup():
    """Instantiates an executor subject to configuration."""
    # Potential future enhancement: allow the default executor to be
    # configured using environment variables (e.g. to select between
    # threads or processes, to choose number of workers, etc.)
    #
    # It is because of this potential future enhancement, that we
    # have moved this logic into a separate function despite it
    # being currently logically quite simple.
    return ProcessPoolExecutor()


def _create_default_executor():
    """Creates an executor and registers appropriate cleanup."""
    result = _create_default_executor_no_cleanup()
    def _cleanup():
        result.shutdown()
    atexit.register(_cleanup)
    return result

# Global default executor so that multiple uses of the adaptor
# do not waste resources creating many duplicative executors.
# Used in the '_get_or_create_default_executor' function below.
_default_executor = None


def _get_or_create_default_executor():
    """Return or lazily instantiate a shared default executor."""
    global _default_executor
    if _default_executor is None:
        _default_executor = _create_default_executor()
    return _default_executor


class _SimpleBlobUploaderAdaptor(BlobUploader):
    """Implementation of 'BlobUploader' wrapping a 'SimpleBlobUploader'.
    
    This implements the core of the function 'blob_uploader_from_simple_blob_uploader'.
    """

    def __init__(self, simple_uploader: SimpleBlobUploader, executor: Optional[Executor]=None):
        self._simple_uploader = simple_uploader
        self._executor = executor or _get_or_create_default_executor()

    def upload_async(self, blob: Blob) -> str:
        full_blob = _with_content_type(blob)
        uri = self._simple_uploader.generate_destination_uri(full_blob)
        self._do_in_background(_UploadAction(self._simple_uploader, uri, full_blob))
        return uri

    def _do_in_background(self, action):
        self._executor.submit(action)



def blob_uploader_from_simple_blob_uploader(simple_uploader: SimpleBlobUploader) -> BlobUploader:
    """Implements a 'BlobUploader' using the supplied 'SimpleBlobUploader'.
    
    The purpose of this function is to allow backend implementations/vendors to be able to
    implement their logic much more simply, using synchronous uploading interfaces.

    This function takes care of the nitty gritty details necessary to supply an asynchronous
    interface on top of the simpler logic supplied by the backend system.
    """
    return _SimpleBlobUploaderAdaptor(simple_uploader)

