# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

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
