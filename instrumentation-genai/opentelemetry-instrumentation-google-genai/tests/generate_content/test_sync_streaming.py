# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


from .nonstreaming_base import NonStreamingTestCase
from .streaming_base import StreamingTestCase


class StreamingMixin:
    @property
    def expected_function_name(self):
        return "google.genai.Models.generate_content_stream"

    def generate_content_stream(self, *args, **kwargs):
        result = []
        for response in self.client.models.generate_content_stream(  # pylint: disable=missing-kwoa
            *args, **kwargs
        ):
            result.append(response)
        return result


class TestGenerateContentStreamingWithSingleResult(
    StreamingMixin, NonStreamingTestCase
):
    def generate_content(self, *args, **kwargs):
        responses = self.generate_content_stream(*args, **kwargs)
        self.assertEqual(len(responses), 1)
        return responses[0]


class TestGenerateContentStreamingWithStreamedResults(
    StreamingMixin, StreamingTestCase
):
    def generate_content(self, *args, **kwargs):
        return self.generate_content_stream(*args, **kwargs)
