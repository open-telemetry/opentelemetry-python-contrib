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

from unittest import mock

import pytest
import requests

from opentelemetry._opamp.proto import opamp_pb2
from opentelemetry._opamp.transport.base import base_headers
from opentelemetry._opamp.transport.exceptions import OpAMPException
from opentelemetry._opamp.transport.requests import RequestsTransport


def test_can_instantiate_requests_transport():
    transport = RequestsTransport()

    assert transport


def test_can_instantiate_requests_transport_with_own_session():
    session = requests.Session()
    transport = RequestsTransport(session=session)

    assert transport
    assert transport.session is session


def test_can_send():
    transport = RequestsTransport()
    serialized_message = opamp_pb2.ServerToAgent().SerializeToString()
    response_mock = mock.Mock(content=serialized_message)
    headers = {"foo": "bar"}
    expected_headers = {**base_headers, **headers}
    data = b""
    with mock.patch.object(transport, "session") as session_mock:
        session_mock.post.return_value = response_mock
        response = transport.send(
            url="http://127.0.0.1/v1/opamp",
            headers=headers,
            data=data,
            timeout_millis=1_000,
            tls_certificate=True,
        )

        session_mock.post.assert_called_once_with(
            "http://127.0.0.1/v1/opamp",
            headers=expected_headers,
            data=data,
            timeout=1,
            verify=True,
            cert=None,
        )

    assert isinstance(response, opamp_pb2.ServerToAgent)


def test_send_tls_certificate_mapped_to_verify():
    transport = RequestsTransport()
    serialized_message = opamp_pb2.ServerToAgent().SerializeToString()
    response_mock = mock.Mock(content=serialized_message)
    data = b""
    with mock.patch.object(transport, "session") as session_mock:
        session_mock.post.return_value = response_mock
        response = transport.send(
            url="https://127.0.0.1/v1/opamp",
            headers={},
            data=data,
            timeout_millis=1_000,
            tls_certificate=False,
        )

        session_mock.post.assert_called_once_with(
            "https://127.0.0.1/v1/opamp",
            headers=base_headers,
            data=data,
            timeout=1,
            verify=False,
            cert=None,
        )

    assert isinstance(response, opamp_pb2.ServerToAgent)


def test_send_mtls():
    transport = RequestsTransport()
    serialized_message = opamp_pb2.ServerToAgent().SerializeToString()
    response_mock = mock.Mock(content=serialized_message)
    data = b""
    with mock.patch.object(transport, "session") as session_mock:
        session_mock.post.return_value = response_mock
        response = transport.send(
            url="https://127.0.0.1/v1/opamp",
            headers={},
            data=data,
            timeout_millis=1_000,
            tls_certificate="server.pem",
            tls_client_certificate="client.pem",
            tls_client_key="client.key",
        )

        session_mock.post.assert_called_once_with(
            "https://127.0.0.1/v1/opamp",
            headers=base_headers,
            data=data,
            timeout=1,
            verify="server.pem",
            cert=("client.pem", "client.key"),
        )

    assert isinstance(response, opamp_pb2.ServerToAgent)


def test_send_mtls_no_client_key():
    transport = RequestsTransport()
    serialized_message = opamp_pb2.ServerToAgent().SerializeToString()
    response_mock = mock.Mock(content=serialized_message)
    data = b""
    with mock.patch.object(transport, "session") as session_mock:
        session_mock.post.return_value = response_mock
        response = transport.send(
            url="https://127.0.0.1/v1/opamp",
            headers={},
            data=data,
            timeout_millis=1_000,
            tls_certificate="server.pem",
            tls_client_certificate="client.pem",
        )

        session_mock.post.assert_called_once_with(
            "https://127.0.0.1/v1/opamp",
            headers=base_headers,
            data=data,
            timeout=1,
            verify="server.pem",
            cert="client.pem",
        )

    assert isinstance(response, opamp_pb2.ServerToAgent)


def test_send_exceptions_raises_opamp_exception():
    transport = RequestsTransport()
    response_mock = mock.Mock()
    headers = {"foo": "bar"}
    expected_headers = {**base_headers, **headers}
    data = b""
    with mock.patch.object(transport, "session") as session_mock:
        session_mock.post.return_value = response_mock
        response_mock.raise_for_status.side_effect = Exception
        with pytest.raises(OpAMPException):
            transport.send(
                url="http://127.0.0.1/v1/opamp",
                headers=headers,
                data=data,
                timeout_millis=1_000,
                tls_certificate=True,
            )

        session_mock.post.assert_called_once_with(
            "http://127.0.0.1/v1/opamp",
            headers=expected_headers,
            data=data,
            timeout=1,
            verify=True,
            cert=None,
        )
