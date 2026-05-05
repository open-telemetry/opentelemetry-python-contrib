# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import asyncio

from .nonstreaming_base import NonStreamingTestCase
from .streaming_base import StreamingTestCase


class AsyncStreamingMixin:
    @property
    def expected_function_name(self):
        return "google.genai.AsyncModels.generate_content_stream"

    async def _generate_content_stream_helper(self, *args, **kwargs):
        result = []
        async for (
            response
        ) in await self.client.aio.models.generate_content_stream(  # pylint: disable=missing-kwoa
            *args, **kwargs
        ):
            result.append(response)
        return result

    def generate_content_stream(self, *args, **kwargs):
        return asyncio.run(
            self._generate_content_stream_helper(*args, **kwargs)
        )


class TestGenerateContentAsyncStreamingWithSingleResult(
    AsyncStreamingMixin, NonStreamingTestCase
):
    def generate_content(self, *args, **kwargs):
        responses = self.generate_content_stream(*args, **kwargs)
        self.assertEqual(len(responses), 1)
        return responses[0]


class TestGenerateContentAsyncStreamingWithStreamedResults(
    AsyncStreamingMixin, StreamingTestCase
):
    def generate_content(self, *args, **kwargs):
        return self.generate_content_stream(*args, **kwargs)
