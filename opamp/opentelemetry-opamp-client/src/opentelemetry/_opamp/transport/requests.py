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

from typing import Mapping

import requests

from opentelemetry._opamp import messages
from opentelemetry._opamp.transport.base import HttpTransport, base_headers
from opentelemetry._opamp.transport.exceptions import OpAMPException


class RequestsTransport(HttpTransport):
    def __init__(self, session: requests.Session | None = None):
        self.session = requests.Session() if session is None else session

    def send(
        self,
        url: str,
        headers: Mapping[str, str],
        data: bytes,
        timeout_millis: int,
    ):
        headers = {**base_headers, **headers}
        timeout: float = timeout_millis / 1e3
        try:
            response = self.session.post(
                url, headers=headers, data=data, timeout=timeout
            )
            response.raise_for_status()
        except Exception:
            raise OpAMPException

        message = messages.decode_message(response.content)

        return message
