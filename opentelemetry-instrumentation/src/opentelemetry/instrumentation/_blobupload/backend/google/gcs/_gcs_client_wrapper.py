from typing import Any, TypeAlias

import logging

_logger = logging.getLogger(__name__)
_gcs_initialized = False
_gcs_client_factory = None
_gcs_blob_from_uri = None


GcsClientType: TypeAlias = Any


def set_gcs_client_factory(gcs_client_type, client_factory):
    global _gcs_initialized
    global _gcs_client_factory
    global GcsClientType
    if _gcs_initialized:
        _logger.warning('Replacing default GCS client factory')
    GcsClientType = gcs_client_type
    _gcs_client_factory = client_factory
    if _gcs_client_factory and _gcs_blob_from_uri:
        _gcs_initialized = True


def set_gcs_blob_from_uri(blob_from_uri):
    global _gcs_initialized
    global _gcs_blob_from_uri
    if _gcs_initialized:
        _logger.warning('Replacing default GCS blob_from_uri method')
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
    set_gcs_blob_from_uri(getattr(_GcsBlob, 'from_uri', getattr(_GcsBlob, 'from_string')))
    _logger.debug('Found "google-cloud-storage" optional dependency and successfully registered it.')
except ImportError:
    _logger.warning('Missing optional "google-cloud-storage" dependency.')
