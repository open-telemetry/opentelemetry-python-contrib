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

"""Defines a simple, synchronous interface for providing a backend implementation."""

import abc

from opentelemetry.instrumentation._blobupload.api import Blob


class SimpleBlobUploader(abc.ABC):
    """Pure abstract base class of a backend implementation that is synchronous."""

    @abc.abstractmethod
    def generate_destination_uri(self, blob: Blob) -> str:
       """Generates a URI of where the blob will get written.

       Args:
         blob: the blob which will be uploaded.

       Returns:
         A new, unique URI that represents the target destination of the data.
       """
       raise NotImplementedError("SimpleBlobUploader.generate_destination_uri")

    @abc.abstractmethod
    def upload_sync(self, uri: str, blob: Blob):
       """Synchronously writes the blob to the specified destination URI.

       Args:
         uri: A destination URI that was previously created by the function
           'create_destination_uri' with the same blob.
         blob: The blob that should get uploaded.

       Effects:
         Attempts to upload/write the Blob to the specified destination URI.
       """
       raise NotImplementedError("SimpleBlobUploader.upload_sync")
