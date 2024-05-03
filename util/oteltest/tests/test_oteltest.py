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
