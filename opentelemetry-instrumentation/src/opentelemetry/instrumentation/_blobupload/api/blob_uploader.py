"""Defines an interface for performing asynchronous blob uploading."""

import abc

from opentelemetry.instrumentation._blobupload.api.blob import Blob
from opentelemetry.instrumentation._blobupload.api.constants import (
    NOT_UPLOADED,
)


class BlobUploader(abc.ABC):
    """Pure abstract base class representing a component that does blob uploading."""

    @abc.abstractmethod
    def upload_async(self, blob: Blob) -> str:
        return NOT_UPLOADED
