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

import asyncio
import logging
import sys
import unittest

sys.path.append("../")

# This needs to go after 'sys.path.append' in order to ensure that 'common'
# can be imported using this naming (when the script is invoked directly).
from common.base import TestCase  # pylint: disable=wrong-import-position


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


class TestGenerateContentAsyncNonstreaming(TestCase):
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

    def generate_content(self, *args, **kwargs):
        return asyncio.run(
            self.client.aio.models.generate_content(*args, **kwargs)
        )

    def test_async_generate_content_not_broken_by_instrumentation(self):
        self.configure_valid_response(response_text="Yep, it works!")
        response = self.generate_content(
            model="gemini-2.0-flash", contents="Does this work?"
        )
        self.assertEqual(response.text, "Yep, it works!")


def main():
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()


if __name__ == "__main__":
    main()
