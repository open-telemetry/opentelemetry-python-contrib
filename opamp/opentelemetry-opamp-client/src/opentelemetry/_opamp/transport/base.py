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

from __future__ import annotations

import abc
from typing import Mapping

from opentelemetry._opamp.proto import opamp_pb2

base_headers = {
    "Content-Type": "application/x-protobuf",
}


class HttpTransport(abc.ABC):
    @abc.abstractmethod
    def send(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        data: bytes,
        timeout_millis: int,
        tls_certificate: str | bool,
        tls_client_certificate: str | None = None,
        tls_client_key: str | None = None,
    ) -> opamp_pb2.ServerToAgent:
        pass
