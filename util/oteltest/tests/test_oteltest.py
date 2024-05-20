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
import pathlib

import pytest

from oteltest import telemetry
from oteltest.private import get_next_json_file, save_telemetry_json


@pytest.fixture
def metric_telemetry():
    return load_json("metric")


@pytest.fixture
def trace_telemetry():
    return load_json("trace")


def load_json(fname):
    fixtures_dir = pathlib.Path(__file__).parent / "fixtures"
    file_path = fixtures_dir / f"{fname}.json"
    with file_path.open("r") as file:
        return json.load(file)


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


def test_telemetry_metric_operations(metric_telemetry):
    tel = telemetry.Telemetry()

    tel.add_metric(metric_telemetry, {}, 1)
    assert {"my-metric-name"} == telemetry.metric_names(tel)
    assert 1 == telemetry.num_metrics(tel)

    tel.add_metric(metric_telemetry, {}, 1)
    assert 2 == telemetry.num_metrics(tel)
    assert {"my-metric-name"} == telemetry.metric_names(tel)


def test_telemetry_trace_operations(trace_telemetry):
    tel = telemetry.Telemetry()
    tel.add_trace(trace_telemetry, {}, 1)
    assert 1 == telemetry.num_spans(tel)
    header_key = "my-trace-header"
    header_val = "my-trace-header-value"
    tel.add_trace(trace_telemetry, {header_key: header_val}, 1)
    assert 2 == telemetry.num_spans(tel)
    assert telemetry.has_trace_header(tel, header_key, header_val)
    assert {"/"} == telemetry.span_names(tel)


def telemetry_from_json(json_str: str) -> telemetry.Telemetry:
    return telemetry_from_dict(json.loads(json_str))


def telemetry_from_dict(d) -> telemetry.Telemetry:
    return telemetry.Telemetry(
        log_requests=d["log_requests"],
        metric_requests=d["metric_requests"],
        trace_requests=d["trace_requests"],
    )
