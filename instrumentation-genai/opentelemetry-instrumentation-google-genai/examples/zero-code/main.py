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

import os

import google.genai


def main():
    client = google.genai.Client()
    response = client.models.generate_content(
        model=os.getenv("MODEL", "gemini-2.0-flash-001"),
        contents=os.getenv("PROMPT", "Why is the sky blue?"),
    )
    print(response.text)


if __name__ == "__main__":
    main()
