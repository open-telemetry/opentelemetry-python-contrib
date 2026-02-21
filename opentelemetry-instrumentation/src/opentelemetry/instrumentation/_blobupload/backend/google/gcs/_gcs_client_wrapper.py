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


"""Isolates calls to 'google-cloud-storage' dependency, simplifying mocking."""


import logging
from typing import Any, TypeAlias

_logger = logging.getLogger(__name__)


# Whether the Google Cloud Storage library has been initialized.
_gcs_initialized = False

# Function that returns a Google Cloud Storage Client object.
_gcs_client_factory = None

# Function that given a URI and client, returns a Google Cloud
# Storage Blob class that can be used to write to a blob.
_gcs_blob_from_uri = None


# Type alias for a Google Cloud Storage client. This has to default
# to 'Any' to allow for mocks of the Google Cloud Storage client. It
# is updated at runtime in 'set_gcs_client_factory', though this
# means it is not particularly useful for automatic static type
# checking (it is, however, useful for documenting intended type).
GcsClientType: TypeAlias = Any


def set_gcs_client_factory(gcs_client_type, client_factory):
    global _gcs_initialized
    global _gcs_client_factory
    global GcsClientType
    if _gcs_initialized:
        _logger.warning("Replacing default GCS client factory")
    GcsClientType = gcs_client_type
    _gcs_client_factory = client_factory
    if _gcs_client_factory and _gcs_blob_from_uri:
        _gcs_initialized = True


def set_gcs_blob_from_uri(blob_from_uri):
    global _gcs_initialized
    global _gcs_blob_from_uri
    if _gcs_initialized:
        _logger.warning("Replacing default GCS blob_from_uri method")
    _gcs_blob_from_uri = blob_from_uri
    if _gcs_client_factory and _gcs_blob_from_uri:
        _gcs_initialized = True


def is_gcs_initialized():
    return _gcs_initialized


def create_gcs_client():
    if _gcs_client_factory is not None:
        return _gcs_client_factory()
    return None


def blob_from_uri(uri, client):
    if _gcs_blob_from_uri is not None:
        return _gcs_blob_from_uri(uri, client=client)
    return None


try:
    from google.cloud.storage import Client as _GcsClient
    from google.cloud.storage.blob import Blob as _GcsBlob
    set_gcs_client_factory(_GcsClient, _GcsClient)
    set_gcs_blob_from_uri(getattr(_GcsBlob, "from_uri", getattr(_GcsBlob, "from_string")))
    _logger.debug('Found "google-cloud-storage" optional dependency and successfully registered it.')
except ImportError:
    _logger.warning('Missing optional "google-cloud-storage" dependency.')
