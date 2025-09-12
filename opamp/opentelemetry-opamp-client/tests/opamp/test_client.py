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

# pylint: disable=no-name-in-module

import json
from unittest import mock

import pytest

from opentelemetry._opamp import messages
from opentelemetry._opamp.client import _HANDLED_CAPABILITIES, OpAMPClient
from opentelemetry._opamp.exceptions import (
    OpAMPRemoteConfigDecodeException,
    OpAMPRemoteConfigParseException,
)
from opentelemetry._opamp.proto import opamp_pb2
from opentelemetry._opamp.proto.anyvalue_pb2 import (
    AnyValue as PB2AnyValue,
)
from opentelemetry._opamp.proto.anyvalue_pb2 import (
    KeyValue as PB2KeyValue,
)
from opentelemetry._opamp.transport.requests import RequestsTransport
from opentelemetry._opamp.version import __version__


@pytest.fixture(name="client")
def client_fixture():
    return OpAMPClient(
        endpoint="url", agent_identifying_attributes={"foo": "bar"}
    )


def test_can_instantiate_opamp_client_with_defaults():
    client = OpAMPClient(
        endpoint="url", agent_identifying_attributes={"foo": "bar"}
    )

    assert client
    assert client._headers == {
        "Content-Type": "application/x-protobuf",
        "User-Agent": "OTel-OpAMP-Python/" + __version__,
    }
    assert client._timeout_millis == 1_000
    assert client._sequence_num == 0
    assert isinstance(client._instance_uid, bytes)
    assert isinstance(client._agent_description, opamp_pb2.AgentDescription)
    assert client._agent_description.identifying_attributes == [
        PB2KeyValue(key="foo", value=PB2AnyValue(string_value="bar")),
    ]
    assert client._agent_description.non_identifying_attributes == []


def test_can_instantiate_opamp_client_all_params():
    transport = RequestsTransport()
    client = OpAMPClient(
        endpoint="url",
        headers={"an": "header"},
        timeout_millis=2_000,
        agent_identifying_attributes={"foo": "bar"},
        agent_non_identifying_attributes={"bar": "baz"},
        transport=transport,
    )

    assert client
    assert client._headers == {
        "Content-Type": "application/x-protobuf",
        "User-Agent": "OTel-OpAMP-Python/" + __version__,
        "an": "header",
    }
    assert client._timeout_millis == 2_000
    assert client._sequence_num == 0
    assert isinstance(client._instance_uid, bytes)
    assert isinstance(client._agent_description, opamp_pb2.AgentDescription)
    assert client._agent_description.identifying_attributes == [
        PB2KeyValue(key="foo", value=PB2AnyValue(string_value="bar")),
    ]
    assert client._agent_description.non_identifying_attributes == [
        PB2KeyValue(key="bar", value=PB2AnyValue(string_value="baz")),
    ]
    assert client._transport is transport


def test_client_headers_override_defaults():
    client = OpAMPClient(
        endpoint="url",
        agent_identifying_attributes={"foo": "bar"},
        headers={"User-Agent": "Custom"},
    )
    client._transport = mock.Mock()
    client._send(b"")

    (send_call,) = client._transport.mock_calls
    assert send_call == mock.call.send(
        url="url",
        headers={
            "Content-Type": "application/x-protobuf",
            "User-Agent": "Custom",
        },
        data=b"",
        timeout_millis=1000,
    )


def test_build_connection_message(client):
    data = client._build_connection_message()

    message = opamp_pb2.AgentToServer()
    message.ParseFromString(data)

    assert message
    assert message.instance_uid == client._instance_uid
    assert message.sequence_num == 0
    assert message.agent_description.identifying_attributes == [
        PB2KeyValue(key="foo", value=PB2AnyValue(string_value="bar")),
    ]
    assert message.agent_description.non_identifying_attributes == []
    assert message.capabilities == _HANDLED_CAPABILITIES


def test_build_connection_message_can_serialize_attributes():
    client = OpAMPClient(
        endpoint="url",
        agent_identifying_attributes={
            "string": "s",
            "bytes": b"b",
            "none": None,
            "bool": True,
            "int": 1,
            "float": 2.0,
        },
    )
    data = client._build_connection_message()

    message = opamp_pb2.AgentToServer()
    message.ParseFromString(data)

    assert message
    assert message.instance_uid == client._instance_uid
    assert message.sequence_num == 0
    assert message.agent_description.identifying_attributes == [
        PB2KeyValue(key="string", value=PB2AnyValue(string_value="s")),
        PB2KeyValue(key="bytes", value=PB2AnyValue(bytes_value=b"b")),
        PB2KeyValue(key="none", value=PB2AnyValue()),
        PB2KeyValue(key="bool", value=PB2AnyValue(bool_value=True)),
        PB2KeyValue(key="int", value=PB2AnyValue(int_value=1)),
        PB2KeyValue(key="float", value=PB2AnyValue(double_value=2.0)),
    ]
    assert message.agent_description.non_identifying_attributes == []
    assert message.capabilities == _HANDLED_CAPABILITIES


def test_build_agent_disconnect_message(client):
    data = client._build_agent_disconnect_message()

    message = opamp_pb2.AgentToServer()
    message.ParseFromString(data)

    assert message
    assert message.instance_uid == client._instance_uid
    assert message.sequence_num == 0
    assert message.agent_disconnect == opamp_pb2.AgentDisconnect()
    assert message.capabilities == _HANDLED_CAPABILITIES


def test_build_heartbeat_message(client):
    data = client._build_heartbeat_message()

    message = opamp_pb2.AgentToServer()
    message.ParseFromString(data)

    assert message
    assert message.instance_uid == client._instance_uid
    assert message.sequence_num == 0
    assert message.capabilities == _HANDLED_CAPABILITIES


def test_update_remote_config_status_without_previous_config(client):
    remote_config_status = client._update_remote_config_status(
        remote_config_hash=b"12345678",
        status=opamp_pb2.RemoteConfigStatuses_APPLIED,
    )

    assert remote_config_status is not None
    assert remote_config_status.last_remote_config_hash == b"12345678"
    assert (
        remote_config_status.status == opamp_pb2.RemoteConfigStatuses_APPLIED
    )
    assert remote_config_status.error_message == ""


def test_update_remote_config_status_with_same_config(client):
    remote_config_status = client._update_remote_config_status(
        remote_config_hash=b"12345678",
        status=opamp_pb2.RemoteConfigStatuses_APPLIED,
    )

    assert remote_config_status is not None

    remote_config_status = client._update_remote_config_status(
        remote_config_hash=b"12345678",
        status=opamp_pb2.RemoteConfigStatuses_APPLIED,
    )

    assert remote_config_status is None


def test_update_remote_config_status_with_diffent_config(client):
    remote_config_status = client._update_remote_config_status(
        remote_config_hash=b"12345678",
        status=opamp_pb2.RemoteConfigStatuses_APPLIED,
    )

    assert remote_config_status is not None

    # different status
    remote_config_status = client._update_remote_config_status(
        remote_config_hash=b"12345678",
        status=opamp_pb2.RemoteConfigStatuses_FAILED,
    )

    assert remote_config_status is not None

    # different error message
    remote_config_status = client._update_remote_config_status(
        remote_config_hash=b"12345678",
        status=opamp_pb2.RemoteConfigStatuses_FAILED,
        error_message="different error message",
    )

    assert remote_config_status is not None

    # different hash
    remote_config_status = client._update_remote_config_status(
        remote_config_hash=b"1234",
        status=opamp_pb2.RemoteConfigStatuses_FAILED,
        error_message="different error message",
    )

    assert remote_config_status is not None


def test_build_remote_config_status_response_message_no_error_message(client):
    remote_config_status = messages._build_remote_config_status_message(
        last_remote_config_hash=b"12345678",
        status=opamp_pb2.RemoteConfigStatuses_APPLIED,
    )
    data = client._build_remote_config_status_response_message(
        remote_config_status
    )

    message = opamp_pb2.AgentToServer()
    message.ParseFromString(data)

    assert message
    assert message.instance_uid == client._instance_uid
    assert message.sequence_num == 0
    assert message.capabilities == _HANDLED_CAPABILITIES
    assert message.remote_config_status
    assert message.remote_config_status.last_remote_config_hash == b"12345678"
    assert (
        message.remote_config_status.status
        == opamp_pb2.RemoteConfigStatuses_APPLIED
    )
    assert not message.remote_config_status.error_message


def test_build_remote_config_status_response_message_with_error_message(
    client,
):
    remote_config_status = messages._build_remote_config_status_message(
        last_remote_config_hash=b"12345678",
        status=opamp_pb2.RemoteConfigStatuses_FAILED,
        error_message="an error message",
    )
    data = client._build_remote_config_status_response_message(
        remote_config_status
    )

    message = opamp_pb2.AgentToServer()
    message.ParseFromString(data)

    assert message
    assert message.instance_uid == client._instance_uid
    assert message.sequence_num == 0
    assert message.capabilities == _HANDLED_CAPABILITIES
    assert message.remote_config_status
    assert message.remote_config_status.last_remote_config_hash == b"12345678"
    assert (
        message.remote_config_status.status
        == opamp_pb2.RemoteConfigStatuses_FAILED
    )
    assert message.remote_config_status.error_message == "an error message"


def test_message_sequence_num_increases_in_send(client):
    client._transport = mock.Mock()
    for index in range(2):
        data = client._build_heartbeat_message()
        client._send(data)

        message = opamp_pb2.AgentToServer()
        message.ParseFromString(data)

        assert message
        assert message.sequence_num == index


def test_send(client):
    client._transport = mock.Mock()
    client._send(b"foo")

    (send_call,) = client._transport.mock_calls
    assert send_call == mock.call.send(
        url="url",
        headers={
            "Content-Type": "application/x-protobuf",
            "User-Agent": "OTel-OpAMP-Python/" + __version__,
        },
        data=b"foo",
        timeout_millis=1000,
    )


def test_decode_remote_config(client):
    config = opamp_pb2.AgentConfigMap()
    config.config_map["application/json"].body = json.dumps(
        {"a": "config"}
    ).encode()
    config.config_map["application/json"].content_type = "application/json"
    config.config_map["text/json"].body = json.dumps(
        {"other": "config"}
    ).encode()
    config.config_map["text/json"].content_type = "text/json"
    message = opamp_pb2.AgentRemoteConfig(config=config)

    decoded = list(client._decode_remote_config(message))
    assert sorted(decoded) == sorted(
        [
            ("application/json", {"a": "config"}),
            ("text/json", {"other": "config"}),
        ]
    )


def test_decode_remote_config_invalid_content_type(client):
    config = opamp_pb2.AgentConfigMap()
    config.config_map["filename"].body = b"1"
    config.config_map["filename"].content_type = "not/json"
    message = opamp_pb2.AgentRemoteConfig(config=config)

    with pytest.raises(OpAMPRemoteConfigParseException):
        list(client._decode_remote_config(message))


def test_decode_remote_config_invalid_file_body(client):
    config = opamp_pb2.AgentConfigMap()
    config.config_map["filename"].body = b"notjson"
    config.config_map["filename"].content_type = "application/json"
    message = opamp_pb2.AgentRemoteConfig(config=config)

    with pytest.raises(OpAMPRemoteConfigDecodeException):
        list(client._decode_remote_config(message))
