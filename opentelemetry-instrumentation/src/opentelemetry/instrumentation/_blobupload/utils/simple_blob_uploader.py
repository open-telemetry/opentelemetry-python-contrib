"""Defines a simple, synchronous interface for providing a backend implementation."""


class SimpleBlobUploader(ABC):
    """Pure abstract base class of a backend implementation that is synchronous."""

   @abstractmethod
   def generate_destination_uri(self, blob: Blob) -> str:
       """Generates a URI of where the blob will get written.
       
       Args:
         blob: the blob which will be uploaded.

       Returns:
         A new, unique URI that represents the target destination of the data.
       """
       raise NotImplementedError('SimpleBlobUploader.generate_destination_uri')

   @abstractmethod
   def upload_sync(self, uri: str, blob: Blob):
       """Synchronously writes the blob to the specified destination URI.

       Args:
         uri: A destination URI that was previously created by the function
           'create_destination_uri' with the same blob.
         blob: The blob that should get uploaded.

       Effects:
         Attempts to upload/write the Blob to the specified destination URI.
       """
       raise NotImplementedError('SimpleBlobUploader.upload_sync')