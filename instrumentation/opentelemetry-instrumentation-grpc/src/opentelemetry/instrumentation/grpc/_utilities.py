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

import grpc

from opentelemetry.trace.status import Status, StatusCode


def _server_status(code, details):
    error_status = Status(
        status_code=StatusCode.ERROR, description=f"{code}:{details}"
    )
    status_codes = {
        grpc.StatusCode.UNKNOWN: error_status,
        grpc.StatusCode.DEADLINE_EXCEEDED: error_status,
        grpc.StatusCode.UNIMPLEMENTED: error_status,
        grpc.StatusCode.INTERNAL: error_status,
        grpc.StatusCode.UNAVAILABLE: error_status,
        grpc.StatusCode.DATA_LOSS: error_status,
    }

    return status_codes.get(
        code, Status(status_code=StatusCode.UNSET, description="")
    )
