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
import dataclasses
import json
from typing import List, Optional


@dataclasses.dataclass
class Request:
    """
    Wraps a grpc message (metric, trace, or log), http headers that came in with the message, and the time elapsed
    between the start of the test the receipt of the message.
    """

    message: dict
    headers: dict
    test_elapsed_ms: int

    def get_header(self, name):
        return self.headers.get(name)

    def to_json(self):
        return json.dumps(self.to_dict())

    def to_dict(self):
        return {
            "request": self.message,
            "headers": self.headers,
            "test_elapsed_ms": self.test_elapsed_ms,
        }


class Telemetry:
    """
    Wraps lists of metric, trace, and log requests sent during a single oteltest script run. An instance is passed in to
    OtelTest#on_stop().
    """

    def __init__(
        self,
        metric_requests: Optional[List[Request]] = None,
        trace_requests: Optional[List[Request]] = None,
        log_requests: Optional[List[Request]] = None,
    ):
        self.metric_requests: List[Request] = metric_requests or []
        self.trace_requests: List[Request] = trace_requests or []
        self.log_requests: List[Request] = log_requests or []

    def add_metric(self, metric: dict, headers: dict, test_elapsed_ms: int):
        self.metric_requests.append(Request(metric, headers, test_elapsed_ms))

    def add_trace(self, trace: dict, headers: dict, test_elapsed_ms: int):
        self.trace_requests.append(Request(trace, headers, test_elapsed_ms))

    def add_log(self, log: dict, headers: dict, test_elapsed_ms: int):
        self.log_requests.append(Request(log, headers, test_elapsed_ms))

    def get_metric_requests(self) -> List[Request]:
        return self.metric_requests

    def get_trace_requests(self) -> List[Request]:
        return self.trace_requests

    def get_logs_requests(self) -> List[Request]:
        return self.log_requests

    def __str__(self):
        return self.to_json()

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)

    def to_dict(self):
        return {
            "metric_requests": [req.to_dict() for req in self.metric_requests],
            "trace_requests": [req.to_dict() for req in self.trace_requests],
            "log_requests": [req.to_dict() for req in self.log_requests],
        }


def num_metrics(telemetry) -> int:
    out = 0
    for req in telemetry.metric_requests:
        for rm in req.message["resourceMetrics"]:
            for sm in rm["scopeMetrics"]:
                out += len(sm["metrics"])
    return out


def metric_names(telemetry) -> set:
    out = set()
    for req in telemetry.metric_requests:
        for rm in req.message["resourceMetrics"]:
            for sm in rm["scopeMetrics"]:
                for metric in sm["metrics"]:
                    out.add(metric["name"])
    return out


def num_spans(telemetry) -> int:
    out = 0
    for req in telemetry.trace_requests:
        for rs in req.message["resourceSpans"]:
            for ss in rs["scopeSpans"]:
                out += len(ss["spans"])
    return out


def span_names(telemetry) -> set:
    out = set()
    for req in telemetry.trace_requests:
        for rs in req.message["resourceSpans"]:
            for spans in rs["scopeSpans"]:
                for span in spans["spans"]:
                    out.add(span["name"])
    return out


def has_trace_header(telemetry, key, expected) -> bool:
    for req in telemetry.trace_requests:
        actual = req.get_header(key)
        if expected == actual:
            return True
    return False
