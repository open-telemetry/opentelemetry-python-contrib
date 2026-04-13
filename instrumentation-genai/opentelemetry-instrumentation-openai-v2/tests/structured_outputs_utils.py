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

"""Shared test definitions for structured outputs (parse) tests."""

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list


STRUCTURED_OUTPUT_PROMPT = [
    {
        "role": "user",
        "content": "Extract the event information from: Team Meeting on 2024-01-15 with Alice and Bob",
    }
]

STRUCTURED_OUTPUT_EXPECTED_INPUT_MESSAGES = [
    {
        "role": "user",
        "parts": [
            {
                "type": "text",
                "content": STRUCTURED_OUTPUT_PROMPT[0]["content"],
            }
        ],
    }
]

EXPECTED_RESPONSE_CONTENT = '{"name": "Team Meeting", "date": "2024-01-15", "participants": ["Alice", "Bob"]}'
