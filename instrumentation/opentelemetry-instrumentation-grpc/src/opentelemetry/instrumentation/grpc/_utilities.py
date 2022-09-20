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

"""Internal utilities."""
from contextlib import contextmanager
from time import time

import grpc
from opentelemetry.metrics import Meter

class RpcInfo:
    def __init__(
        self,
        full_method=None,
        metadata=None,
        timeout=None,
        request=None,
        response=None,
        error=None,
    ):
        self.full_method = full_method
        self.metadata = metadata
        self.timeout = timeout
        self.request = request
        self.response = response
        self.error = error


class _TimedMetricRecorder:
    def __init__(self, meter: Meter, kind: str):
        self._meter = meter
        self._kind = kind

        self._duration = self._meter.create_histogram(
            name=f"rpc.{kind}.duration",
            description="measures duration of RPC",
            unit="ms",
        )
        self._request_size = self._meter.create_histogram(
            name=f"rpc.{kind}.request.size",
            description="measures size of RPC request messages (uncompressed)",
            unit="By",
        )
        self._response_size = self._meter.create_histogram(
            name=f"rpc.{kind}.response.size",
            description="measures size of RPC response messages (uncompressed)",
            unit="By",
        )
        self._request_count = self._meter.create_histogram(
            name=f"rpc.{kind}.requests_per_rpc",
            description="measures the number of messages received per RPC. Should be 1 for all non-streaming RPCs",
            unit="1",
        )
        self._response_count = self._meter.create_counter(
            name=f"rpc.{kind}.responses_per_rpc",
            description="measures the number of messages sent per RPC. Should be 1 for all non-streaming RPCs",
            unit="1",
        )

    def record_request_size(self, size, method):
        labels = {"rpc.method": method}
        self._request_size.record(size, labels)

    def record_response_size(self, size, method):
        labels = {"rpc.method": method}
        self._response_size.record(size, labels)

    def record_request_count(self, count, method):
        labels = {"rpc.method": method}
        self._request_count.record(count, labels)

    def record_response_count(self, count, method):
        labels = {"rpc.method": method}
        self._response_count.record(count, labels)


    @contextmanager
    def record_duration(self, method):
        start_time = time()
        labels = {
            "rpc.method": method,
            "rpc.system": "grpc",
            "rpc.grpc.status_code": grpc.StatusCode.OK.name,
        }
        try:
            yield labels
        except grpc.RpcError as exc:  # pylint:disable=no-member
            # pylint: disable=no-member
            labels["rpc.grpc.status_code"] = exc.code().name
            labels["error"] = "true"
            raise
        finally:
            elapsed_time = (time() - start_time) * 1000
            self._duration.record(elapsed_time, labels)