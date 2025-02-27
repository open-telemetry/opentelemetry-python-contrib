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
