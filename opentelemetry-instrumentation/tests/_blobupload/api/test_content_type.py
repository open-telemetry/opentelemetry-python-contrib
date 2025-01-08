#! /usr/bin/env python3

if __name__ == '__main__':
    import sys
    sys.path.append('../../../src')

from opentelemetry.instrumentation._blobupload.api import detect_content_type
from PIL import Image

import io
import unittest


def create_test_image(format):
    """Helper for creating a PIL Image for verifying image format support."""
    test_img = Image.new('RGB', (2, 2))
    output_buffer = io.BytesIO()
    test_img.save(output_buffer, format)
    result = output_buffer.getvalue()
    output_buffer.close()
    test_img.close()
    return result


class TestContentType(unittest.TestCase):

    def test_detects_plaintext(self):
        input = 'this is just regular text'
        output = detect_content_type(input.encode())
        self.assertEqual(output, 'text/plain')

    def test_detects_json(self):
        input = '''{
            "this": {
                "contains": "json"
            }
        }'''
        output = detect_content_type(input.encode())
        self.assertEqual(output, 'application/json')

    def test_detects_jpeg(self):
        input = create_test_image('jpeg')
        output = detect_content_type(input)
        self.assertEqual(output, 'image/jpeg')

    def test_detects_png(self):
        input = create_test_image('png')
        output = detect_content_type(input)
        self.assertEqual(output, 'image/png')


if __name__ == '__main__':
    unittest.main()