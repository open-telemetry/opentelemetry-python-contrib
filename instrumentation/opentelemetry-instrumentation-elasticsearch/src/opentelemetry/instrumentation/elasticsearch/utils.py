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


# pylint: disable=C0103
def _flatten_dict(d, parent_key=""):
    items = []
    for k, v in d.items():
        new_key = parent_key + "." + k if parent_key else k
        # recursive call _flatten_dict for a non-empty dict value
        if isinstance(v, dict) and v:
            items.extend(_flatten_dict(v, new_key).items())
        else:
            items.append((new_key, v))
    return dict(items)


def _unflatten_dict(d):
    res = {}
    for k, v in d.items():
        keys = k.split(".")
        d = res
        for key in keys[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[keys[-1]] = v
    return res


def sanitize_body(body) -> str:
    if isinstance(body, str):
        body = json.loads(body)

    flatten_body = _flatten_dict(body)

    for key in flatten_body:
        if key.endswith(sanitized_keys):
            flatten_body[key] = sanitized_value

    return str(_unflatten_dict(flatten_body))
