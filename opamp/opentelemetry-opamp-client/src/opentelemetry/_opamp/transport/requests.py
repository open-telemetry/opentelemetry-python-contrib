# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from typing import Mapping

import requests

from opentelemetry._opamp import messages
from opentelemetry._opamp.transport.base import HttpTransport, base_headers
from opentelemetry._opamp.transport.exceptions import OpAMPException

logger = logging.getLogger(__name__)


class RequestsTransport(HttpTransport):
    def __init__(self, session: requests.Session | None = None):
        self.session = requests.Session() if session is None else session

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
    ):
        headers = {**base_headers, **headers}
        timeout: float = timeout_millis / 1e3
        client_cert = (
            (tls_client_certificate, tls_client_key)
            if tls_client_certificate and tls_client_key
            else tls_client_certificate
        )
        try:
            response = self.session.post(
                url,
                headers=headers,
                data=data,
                timeout=timeout,
                verify=tls_certificate,
                cert=client_cert,
            )
            response.raise_for_status()
        except Exception as exc:
            raise OpAMPException(str(exc)) from exc

        message = messages.decode_message(response.content)

        return message
