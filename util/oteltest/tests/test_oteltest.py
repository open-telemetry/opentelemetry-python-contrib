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

from oteltest import Telemetry
from oteltest.private import get_next_json_file, save_telemetry_json


def test_get_next_json_file(tmp_path):
    module_name = "my_module_name"
    path_to_dir = str(tmp_path)

    next_file = get_next_json_file(path_to_dir, module_name)
    assert "my_module_name.0.json" == next_file

    save_telemetry_json(path_to_dir, next_file, "")

    next_file = get_next_json_file(path_to_dir, module_name)
    assert "my_module_name.1.json" == next_file

    save_telemetry_json(path_to_dir, next_file, "[1]")

    next_file = get_next_json_file(path_to_dir, module_name)
    assert "my_module_name.2.json" == next_file


def test_telemetry():
    t = Telemetry()
    t.add_log({}, {}, 0)



def json_to_telemetry(json_str: str) -> Telemetry:
    return dict_to_telemetry(json.loads(json_str))


def dict_to_telemetry(d) -> Telemetry:
    return Telemetry(
        log_requests=d["log_requests"],
        metric_requests=d["metric_requests"],
        trace_requests=d["trace_requests"],
    )
