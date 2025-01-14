#! /usr/bin/env python3

if __name__ == "__main__":
    import sys
    sys.path.append("../../../../../src")

import logging
import unittest
from multiprocessing import Queue

from opentelemetry.instrumentation._blobupload.api import (
    Blob,
    BlobUploader,
    generate_labels_for_event,
    generate_labels_for_span,
    generate_labels_for_span_event,
)

# Internal implementation used for mocking
from opentelemetry.instrumentation._blobupload.backend.google.gcs import (
    GcsBlobUploader,
    _gcs_client_wrapper,
)


class FakeGcs(object):

    def __init__(self):
        self._queue = Queue()
        self._storage = {}
        self._done = set()

    def reset(self):
        self._storage = {}

    def get(self, gcs_blob_id):
        while gcs_blob_id not in self._done:
            self._queue.get()
        return self._storage.get(gcs_blob_id)

    def upload_from_file(self, gcs_blob_id, data, content_type):
        b = Blob(data.read(), content_type=content_type)
        self._storage[gcs_blob_id] = b

    def update_metadata(self, gcs_blob_id, new_metadata):
        old = self._storage[gcs_blob_id]
        b = Blob(old.raw_bytes, content_type=old.content_type, labels=new_metadata)
        self._storage[gcs_blob_id] = b
        self._done.add(gcs_blob_id)
        self._queue.put(gcs_blob_id)


class FakeGcsBlob(object):

    def __init__(self, gcs_blob_id, fake_gcs):
        self._gcs_blob_id = gcs_blob_id
        self._fake_gcs = fake_gcs
        self._metadata = {}

    def upload_from_file(self, iodata, content_type):
        self._fake_gcs.upload_from_file(self._gcs_blob_id, iodata, content_type)

    @property
    def metadata(self):
        self._metadata

    @metadata.setter
    def metadata(self, m):
        self._metadata = m
        self._fake_gcs.update_metadata(self._gcs_blob_id, self._metadata)


def mocked_blob_from_uri(fake_gcs):
    def gcs_blob_from_uri(uri, client):
        return FakeGcsBlob(uri, fake_gcs)
    return gcs_blob_from_uri


_gcs_mock = FakeGcs()
_gcs_client_wrapper.set_gcs_client_factory(FakeGcs, lambda: _gcs_mock)
_gcs_client_wrapper.set_gcs_blob_from_uri(mocked_blob_from_uri(_gcs_mock))


def get_from_fake_gcs(gcs_blob_id):
    return _gcs_mock.get(gcs_blob_id)


class GcsBlobUploaderTestCase(unittest.TestCase):

    def setUp(self):
       _gcs_mock.reset()

    def test_constructor_throws_if_prefix_not_uri(self):
        with self.assertRaises(ValueError):
            GcsBlobUploader("not a valgcs_blob_id URI")

    def test_constructor_throws_if_prefix_not_gs_protocol(self):
        with self.assertRaises(ValueError):
            GcsBlobUploader("other://foo/bar")

    def test_can_construct_gcs_uploader_with_bucket_uri(self):
        uploader = GcsBlobUploader("gs://some-bucket")
        self.assertIsNotNone(uploader)
        self.assertIsInstance(uploader, BlobUploader)

    def test_can_construct_gcs_uploader_with_bucket_uri_and_trailing_slash(self):
        uploader = GcsBlobUploader("gs://some-bucket/")
        self.assertIsNotNone(uploader)
        self.assertIsInstance(uploader, BlobUploader)

    def test_can_construct_gcs_uploader_with_bucket_and_path_uri(self):
        uploader = GcsBlobUploader("gs://some-bucket/some/path")
        self.assertIsNotNone(uploader)
        self.assertIsInstance(uploader, BlobUploader)

    def test_can_construct_gcs_uploader_with_bucket_and_path_uri_with_trailing_slash(self):
        uploader = GcsBlobUploader("gs://some-bucket/some/path/")
        self.assertIsNotNone(uploader)
        self.assertIsInstance(uploader, BlobUploader)

    def test_uploads_blob_from_span(self):
        trace_id = "test-trace-id"
        span_id = "test-span-id"
        labels = generate_labels_for_span(trace_id, span_id)
        blob = Blob("some data".encode(), content_type="text/plain", labels=labels)
        uploader = GcsBlobUploader("gs://some-bucket/some/path")
        url = uploader.upload_async(blob)
        self.assertTrue(
            url.startswith("gs://some-bucket/some/path/traces/test-trace-id/spans/test-span-id/uploads/")
        )
        uploaded_blob = get_from_fake_gcs(url)
        self.assertEqual(blob, uploaded_blob)

    def test_uploads_blob_from_event(self):
        trace_id = "test-trace-id"
        span_id = "test-span-id"
        event_name = "event-name"
        labels = generate_labels_for_event(trace_id, span_id, event_name)
        blob = Blob("some data".encode(), content_type="text/plain", labels=labels)
        uploader = GcsBlobUploader("gs://some-bucket/some/path")
        url = uploader.upload_async(blob)
        self.assertTrue(
            url.startswith("gs://some-bucket/some/path/traces/test-trace-id/spans/test-span-id/events/event-name/uploads/")
        )
        uploaded_blob = get_from_fake_gcs(url)
        self.assertEqual(blob, uploaded_blob)

    def test_uploads_blob_from_span_event(self):
        trace_id = "test-trace-id"
        span_id = "test-span-id"
        event_name = "event-name"
        event_index = 2
        labels = generate_labels_for_span_event(trace_id, span_id, event_name, event_index)
        blob = Blob("some data".encode(), content_type="text/plain", labels=labels)
        uploader = GcsBlobUploader("gs://some-bucket/some/path")
        url = uploader.upload_async(blob)
        self.assertTrue(
            url.startswith("gs://some-bucket/some/path/traces/test-trace-id/spans/test-span-id/events/2/uploads/")
        )
        uploaded_blob = get_from_fake_gcs(url)
        self.assertEqual(blob, uploaded_blob)

    def test_uploads_blobs_missing_expected_labels(self):
        blob = Blob("some data".encode(), content_type="text/plain")
        uploader = GcsBlobUploader("gs://some-bucket/some/path")
        url = uploader.upload_async(blob)
        self.assertTrue(
            url.startswith("gs://some-bucket/some/path/uploads/"),
        )
        uploaded_blob = get_from_fake_gcs(url)
        self.assertEqual(blob, uploaded_blob)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
