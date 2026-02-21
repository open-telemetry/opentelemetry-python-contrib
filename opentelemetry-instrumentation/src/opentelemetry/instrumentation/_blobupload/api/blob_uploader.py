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
