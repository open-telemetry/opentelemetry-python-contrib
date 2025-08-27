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

from dataclasses import dataclass


@dataclass
class Message:
    content: str
    type: str
    name: str

    def _to_part_dict(self):
        """Convert the message to a dictionary suitable for OpenTelemetry semconvs.

        Ref: https://github.com/open-telemetry/semantic-conventions/blob/main/docs/registry/attributes/gen-ai.md#gen-ai-input-messages
        """

        # TODO: Support tool_call and tool_call response
        return {
            "role": self.type,
            "parts": [
                {
                    "content": self.content,
                    "type": "text",
                }
            ],
        }


@dataclass
class ChatGeneration:
    content: str
    type: str
    finish_reason: str = None


@dataclass
class Error:
    message: str
    type: type[BaseException]
