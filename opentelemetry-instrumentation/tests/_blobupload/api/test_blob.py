#! /usr/bin/env python3

if __name__ == "__main__":
    import sys
    sys.path.append("../../../src")

import base64
import logging
import unittest

from opentelemetry.instrumentation._blobupload.api import Blob


class TestBlob(unittest.TestCase):

    def test_construction_with_just_bytes(self):
        data = "some string".encode()
        blob = Blob(data)
        self.assertEqual(blob.raw_bytes, data)
        self.assertIsNone(blob.content_type)
        self.assertIsNotNone(blob.labels)
        self.assertEqual(len(blob.labels), 0)

    def test_construction_with_bytes_and_content_type(self):
        data = "some string".encode()
        content_type = "text/plain"
        blob = Blob(data, content_type=content_type)
        self.assertEqual(blob.raw_bytes, data)
        self.assertEqual(blob.content_type, content_type)
        self.assertIsNotNone(blob.labels)
        self.assertEqual(len(blob.labels), 0)

    def test_construction_with_bytes_and_labels(self):
        data = "some string".encode()
        labels = {"key1": "value1", "key2": "value2"}
        blob = Blob(data, labels=labels)
        self.assertEqual(blob.raw_bytes, data)
        self.assertIsNone(blob.content_type)
        self.assert_labels_equal(blob.labels, labels)

    def test_construction_with_all_fields(self):
        data = "some string".encode()
        content_type = "text/plain"
        labels = {"key1": "value1", "key2": "value2"}
        blob = Blob(data, content_type=content_type, labels=labels)
        self.assertEqual(blob.raw_bytes, data)
        self.assertEqual(blob.content_type, content_type)
        self.assert_labels_equal(blob.labels, labels)

    def test_from_data_uri_without_labels(self):
        data = "some string".encode()
        content_type = "text/plain"
        encoded_data = base64.b64encode(data).decode()
        uri = "data:{};base64,{}".format(content_type, encoded_data)
        blob = Blob.from_data_uri(uri)
        self.assertEqual(blob.raw_bytes, data)
        self.assertEqual(blob.content_type, content_type)
        self.assertIsNotNone(blob.labels)
        self.assertEqual(len(blob.labels), 0)

    def test_from_data_uri_with_labels(self):
        data = "some string".encode()
        content_type = "text/plain"
        encoded_data = base64.b64encode(data).decode()
        uri = "data:{};base64,{}".format(content_type, encoded_data)
        labels = {"key1": "value1", "key2": "value2"}
        blob = Blob.from_data_uri(uri, labels=labels)
        self.assertEqual(blob.raw_bytes, data)
        self.assertEqual(blob.content_type, content_type)
        self.assert_labels_equal(blob.labels, labels)

    def test_from_data_uri_with_valid_standard_base64(self):
        data = "some string".encode()
        content_type = "text/plain"
        encoded_data = base64.standard_b64encode(data).decode()
        uri = "data:{};base64,{}".format(content_type, encoded_data)
        blob = Blob.from_data_uri(uri)
        self.assertEqual(blob.raw_bytes, data)
        self.assertEqual(blob.content_type, content_type)

    def test_from_data_uri_with_valid_websafe_base64(self):
        data = "some string".encode()
        content_type = "text/plain"
        encoded_data = base64.urlsafe_b64encode(data).decode()
        uri = "data:{};base64,{}".format(content_type, encoded_data)
        blob = Blob.from_data_uri(uri)
        self.assertEqual(blob.raw_bytes, data)
        self.assertEqual(blob.content_type, content_type)

    def test_from_data_uri_with_non_data_uri_content(self):
        with self.assertRaisesRegex(ValueError, 'expected "data:" prefix'):
            Blob.from_data_uri("not a valid data uri")

    def test_from_data_uri_with_non_base64_content(self):
        with self.assertRaisesRegex(ValueError, 'expected ";base64," section'):
            Blob.from_data_uri("data:text/plain,validifpercentencoded")

    def assert_labels_equal(self, a, b):
        self.assertEqual(len(a), len(b), msg="Different sizes: {} vs {}; a={}, b={}".format(len(a), len(b), a, b))
        for k in a:
            self.assertTrue(k in b, msg="Key {} found in a but not b".format(k))
            va = a[k]
            vb = b[k]
            self.assertEqual(va, vb, msg="Values for key {} different for a vs b: {} vs {}".format(k, va, vb))


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
