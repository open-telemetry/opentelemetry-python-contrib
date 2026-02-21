#! /usr/bin/env python3

if __name__ == "__main__":
    import sys
    sys.path.append("../../../src")

import logging
import unittest

from opentelemetry.instrumentation._blobupload.api import (
    NOT_UPLOADED,
    Blob,
    BlobUploader,
    BlobUploaderProvider,
    get_blob_uploader,
    set_blob_uploader_provider,
)


class TestProvider(unittest.TestCase):

    def test_default_provider(self):
        uploader = get_blob_uploader("test")
        self.assertIsNotNone(uploader)
        blob = Blob(bytes())
        url = uploader.upload_async(blob)
        self.assertEqual(url, NOT_UPLOADED)

    def test_custom_provider(self):

        class CustomUploader(BlobUploader):

            def __init__(self, result):
                self.captured_blob = None
                self.upload_result = result

            def upload_async(self, blob):
                self.captured_blob = blob
                return self.upload_result

        class CustomProvider(BlobUploaderProvider):

            def __init__(self, uploader):
                self.uploader = uploader
                self.captured_use_case = None

            def get_blob_uploader(self, use_case):
                self.captured_use_case = use_case
                return self.uploader

        uploader = CustomUploader("foo")
        provider = CustomProvider(uploader)
        old_provider = set_blob_uploader_provider(provider)
        returned_uploader = get_blob_uploader("test")
        self.assertEqual(provider.captured_use_case, "test")
        self.assertEqual(returned_uploader, uploader)
        blob = Blob(bytes(), content_type="bar")
        url = returned_uploader.upload_async(blob)
        self.assertEqual(url, "foo")
        self.assertEqual(uploader.captured_blob, blob)
        unset_provider = set_blob_uploader_provider(old_provider)
        self.assertEqual(unset_provider, provider)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
