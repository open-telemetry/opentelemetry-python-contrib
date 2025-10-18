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
import json

sanitized_keys = (
    "message",
    "should",
    "filter",
    "query",
    "queries",
    "intervals",
    "match",
)
sanitized_value = "?"



def sanitize_dict(d):
    sanitized_copy = {}
    for key, value in d.items():
        if isinstance(value, dict):
            sanitized_copy[key] = sanitize_dict(value)
        elif key in sanitized_keys:
            sanitized_copy[key] = sanitized_value
        else:
            sanitized_copy[key] = value
    return sanitized_copy


def sanitize_body(body) -> str:
    if isinstance(body, str):
        body = json.loads(body)

    sanitized_body = sanitize_dict(body)
    return str(sanitized_body)
