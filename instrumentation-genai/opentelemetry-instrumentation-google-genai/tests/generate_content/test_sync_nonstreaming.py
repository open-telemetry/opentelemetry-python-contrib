#!./run_with_env.sh

import unittest
import sys
sys.path.append('../')

from common.base import TestCase


class TestGenerateContentSyncNonstreaming(TestCase):

    def test_generates_span(self):
        self.requests.add_response({
            'modelVersion': 'gemini-2.0-flash-test123',
            'candidates': [{
                'content': {
                    'role': 'model',
                    'parts': [{
                        'text': 'Yep, it works!'
                    }],
                }
            }]
        })
        response = self.client.models.generate_content(
            model='gemini-2.0-flash',
            contents='Does this work?')
        self.assertEqual(response.text, 'Yep, it works!')
        self.otel.assert_has_span_named('google.genai.Models.generate_content')

    def test_generated_span_has_minimal_genai_attributes(self):
        self.requests.add_response({
            'modelVersion': 'gemini-2.0-flash-test123',
            'candidates': [{
                'content': {
                    'role': 'model',
                    'parts': [{
                        'text': 'Yep, it works!'
                    }],
                }
            }]
        })
        response = self.client.models.generate_content(
            model='gemini-2.0-flash',
            contents='Does this work?')
        self.assertEqual(response.text, 'Yep, it works!')
        self.otel.assert_has_span_named('google.genai.Models.generate_content')
        span = self.otel.get_span_named('google.genai.Models.generate_content')
        self.assertEqual(span.attributes['gen_ai.system'], 'gemini')
        self.assertEqual(span.attributes['gen_ai.operation.name'], 'GenerateContent')


def main():
    unittest.main()


if __name__  == '__main__':
    main()
