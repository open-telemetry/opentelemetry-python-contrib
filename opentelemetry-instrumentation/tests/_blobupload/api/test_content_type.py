#! /usr/bin/env python3

if __name__ == "__main__":
    import sys
    sys.path.append("../../../src")

import io
import logging
import unittest

from PIL import Image

from opentelemetry.instrumentation._blobupload.api import detect_content_type


def create_test_image(image_format):
    """Helper for creating a PIL Image for verifying image format support."""
    test_img = Image.new("RGB", (2, 2))
    output_buffer = io.BytesIO()
    test_img.save(output_buffer, image_format)
    result = output_buffer.getvalue()
    output_buffer.close()
    test_img.close()
    return result


class TestContentType(unittest.TestCase):

    def test_handles_empty_correctly(self):
        data = bytes()
        content_type = detect_content_type(data)
        self.assertEqual(content_type, "application/octet-stream")

    def test_detects_plaintext(self):
        data = "this is just regular text"
        content_type = detect_content_type(data.encode())
        self.assertEqual(content_type, "text/plain")

    def test_detects_json(self):
        data = """{
            "this": {
                "contains": "json"
            }
        }"""
        content_type = detect_content_type(data.encode())
        self.assertEqual(content_type, "application/json")

    def test_detects_jpeg(self):
        data = create_test_image("jpeg")
        content_type = detect_content_type(data)
        self.assertEqual(content_type, "image/jpeg")

    def test_detects_png(self):
        data = create_test_image("png")
        content_type = detect_content_type(data)
        self.assertEqual(content_type, "image/png")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
