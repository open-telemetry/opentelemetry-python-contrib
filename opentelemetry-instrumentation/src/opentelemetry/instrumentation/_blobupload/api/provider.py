import abc
import logging
from typing import Optional

from opentelemetry.instrumentation._blobupload.api.blob import Blob
from opentelemetry.instrumentation._blobupload.api.blob_uploader import (
    BlobUploader,
)

_logger = logging.getLogger(__name__)


class _NoOpBlobUploader(BlobUploader):
    """Implementation of BlobUploader that does nothing."""

    def upload_async(self, blob: Blob) -> str:
        return NOT_UPLOADED


class BlobUploaderProvider(abc.ABC):
    """Pure abstract base for configuring how to provide a BlobUploader."""

    def get_blob_uploader(self, use_case: Optional[str]) -> BlobUploader:
        """Returns a BlobUploader for the specified use case.

        Args:
          use_case: An optional use case that describes what the uploader is for. This could
            name a particular package, class, or instrumentation. It is intended to allow
            users to differentiate upload behavior based on the target instrumentation.

        Returns:
          A BlobUploader that is appropriate for the use case.
        """
        return _NoOpBlobUploader()


class _DefaultBlobUploaderProvider(BlobUploaderProvider):
    """Default provider used when none has been configured."""

    def get_blob_uploader(self, use_case: Optional[str]) -> BlobUploader:
        use_case_formatted = "(None)"
        if use_case:
            use_case_formatted = use_case
        _logger.warning(
            "No BlobUploaderProvider configured; returning a no-op for use case {}".format(
                use_case_formatted
            )
        )
        return _NoOpBlobUploader()


_blob_uploader_provider = _DefaultBlobUploaderProvider()


def set_blob_uploader_provider(provider: BlobUploaderProvider):
    """Allows configuring the behavior of 'get_blob_uploader."""
    global _blob_uploader_provider
    _blob_uploader_provider = provider


def get_blob_uploader(use_case: Optional[str] = None) -> BlobUploader:
    return _blob_uploader_provider.get_blob_uploader(use_case)
