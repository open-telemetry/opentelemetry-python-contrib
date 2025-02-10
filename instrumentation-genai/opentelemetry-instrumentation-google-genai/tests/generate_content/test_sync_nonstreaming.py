#!./run_with_env.sh

import unittest
import sys
sys.path.append('../')

from common.base import TestCase


class TestGenerateContentSyncNonstreaming(TestCase):

    def setUp(self):
        super().setUp()

    def configure_valid_response(self, response_text='The model_response', input_tokens=10, output_tokens=20):
        self.requests.add_response({
            'modelVersion': 'gemini-2.0-flash-test123',
            'usageMetadata': {
                'promptTokenCount': input_tokens,
                'candidatesTokenCount': output_tokens,
                'totalTokenCount': input_tokens + output_tokens,
            },
            'candidates': [{
                'content': {
                    'role': 'model',
                    'parts': [{
                        'text': response_text,
                    }],
                }
            }]
        })

    def test_generates_span(self):
        self.configure_valid_response(response_text='Yep, it works!')
        response = self.client.models.generate_content(
            model='gemini-2.0-flash',
            contents='Does this work?')
        self.assertEqual(response.text, 'Yep, it works!')
        self.otel.assert_has_span_named('google.genai.Models.generate_content')

    def test_generated_span_has_minimal_genai_attributes(self):
        self.configure_valid_response(response_text='Yep, it works!')
        self.client.models.generate_content(
            model='gemini-2.0-flash',
            contents='Does this work?')
        self.otel.assert_has_span_named('google.genai.Models.generate_content')
        span = self.otel.get_span_named('google.genai.Models.generate_content')
        self.assertEqual(span.attributes['gen_ai.system'], 'gemini')
        self.assertEqual(span.attributes['gen_ai.operation.name'], 'GenerateContent')

    def test_generated_span_counts_tokens(self):
        self.configure_valid_response(input_tokens=123, output_tokens=456)
        response = self.client.models.generate_content(
            model='gemini-2.0-flash',
            contents='Some input')
        self.otel.assert_has_span_named('google.genai.Models.generate_content')
        span = self.otel.get_span_named('google.genai.Models.generate_content')
        self.assertEqual(span.attributes['gen_ai.usage.input_tokens'], 123)
        self.assertEqual(span.attributes['gen_ai.usage.output_tokens'], 456)


def main():
    unittest.main()


if __name__  == '__main__':
    main()
