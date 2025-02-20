#!./run_with_env.sh

# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# TODO: once the async streaming case has been implemented, we should have
# two different tests here that inherit from "streaming_base" and "nonstreaming_base",
# covering the cases of one response and multiple streaming responses.

import asyncio
import logging
import unittest

from ..common.base import TestCase


def create_valid_response(
    response_text="The model response", input_tokens=10, output_tokens=20
):
    return {
        "modelVersion": "gemini-2.0-flash-test123",
        "usageMetadata": {
            "promptTokenCount": input_tokens,
            "candidatesTokenCount": output_tokens,
            "totalTokenCount": input_tokens + output_tokens,
        },
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "text": response_text,
                        }
                    ],
                }
            }
        ],
    }


# Temporary test fixture just to ensure that the in-progress work to
# implement this case doesn't break the original code.
class TestGenerateContentAsyncStreaming(TestCase):
    def configure_valid_response(
        self,
        response_text="The model_response",
        input_tokens=10,
        output_tokens=20,
    ):
        self.requests.add_response(
            create_valid_response(
                response_text=response_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

    async def _generate_content_helper(self, *args, **kwargs):
        result = []
        async for (
            response
        ) in await self.client.aio.models.generate_content_stream(
            *args, **kwargs
        ):
            result.append(response)
        return result

    def generate_content(self, *args, **kwargs):
        return asyncio.run(self._generate_content_helper(*args, **kwargs))

    def test_async_generate_content_not_broken_by_instrumentation(self):
        self.configure_valid_response(response_text="Yep, it works!")
        responses = self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].text, "Yep, it works!")


def main():
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()


if __name__ == "__main__":
    main()
