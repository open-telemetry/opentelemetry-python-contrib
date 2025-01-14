#! /usr/bin/env python3

if __name__ == "__main__":
    import sys
    sys.path.append("../../../src")

import logging
import unittest
from multiprocessing import Queue

from opentelemetry.instrumentation._blobupload.api import Blob, BlobUploader
from opentelemetry.instrumentation._blobupload.utils import (
    SimpleBlobUploader,
    blob_uploader_from_simple_blob_uploader,
)


class QueueBasedUploader(SimpleBlobUploader):

    def __init__(self, queue):
        self._queue = queue

    def generate_destination_uri(self, blob):
        return blob.labels["destination_uri"]

    def upload_sync(self, uri, blob):
        self._queue.put((uri, blob))


class FailingUploader(SimpleBlobUploader):

    def __init__(self, queue):
        self._queue = queue

    def generate_destination_uri(self, blob):
        return blob.labels["destination_uri"]

    def upload_sync(self, uri, blob):
        try:
            raise RuntimeError("something went wrong")
        finally:
            self._queue.put("done")



class TestBlob(unittest.TestCase):

    def test_simple_blob_uploader_adaptor(self):
        queue = Queue()
        simple = QueueBasedUploader(queue)
        blob = Blob(bytes(), content_type="some-content-type", labels={"destination_uri": "foo"})
        uploader = blob_uploader_from_simple_blob_uploader(simple)
        self.assertIsInstance(uploader, BlobUploader)
        url = uploader.upload_async(blob)
        self.assertEqual(url, "foo")
        stored_uri, stored_blob = queue.get()
        self.assertEqual(stored_uri, "foo")
        self.assertEqual(stored_blob, blob)
        self.assertTrue(queue.empty())
        queue.close()

    def test_auto_adds_missing_content_type(self):
        queue = Queue()
        simple = QueueBasedUploader(queue)
        blob = Blob("some plain text".encode(),  labels={"destination_uri": "foo"})
        uploader = blob_uploader_from_simple_blob_uploader(simple)
        self.assertIsInstance(uploader, BlobUploader)
        url = uploader.upload_async(blob)
        self.assertEqual(url, "foo")
        stored_uri, stored_blob = queue.get()
        self.assertEqual(stored_uri, "foo")
        self.assertEqual(stored_blob.raw_bytes, blob.raw_bytes)
        self.assertEqual(stored_blob.content_type, "text/plain")
        self.assertEqual(stored_blob.labels, blob.labels)
        self.assertTrue(queue.empty())
        queue.close()

    def test_captures_exceptions_raised(self):
        queue = Queue()
        simple = FailingUploader(queue)
        blob = Blob(bytes(),  labels={"destination_uri": "foo"})
        uploader = blob_uploader_from_simple_blob_uploader(simple)
        self.assertIsInstance(uploader, BlobUploader)
        url = uploader.upload_async(blob)
        self.assertEqual(url, "foo")
        queue.get()
        self.assertTrue(queue.empty())
        queue.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
