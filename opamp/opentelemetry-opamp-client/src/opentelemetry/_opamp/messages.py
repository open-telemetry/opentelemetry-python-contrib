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
# FIXME: remove this after _opamp -> opamp, making this helpers public is not enough for pyright
# type: ignore[reportUnusedFunction]

from __future__ import annotations

import json
from typing import Generator, Mapping

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
from opentelemetry.util.types import AnyValue


def _decode_message(data: bytes) -> opamp_pb2.ServerToAgent:
    message = opamp_pb2.ServerToAgent()
    message.ParseFromString(data)
    return message


def _encode_value(value: AnyValue) -> PB2AnyValue:
    if value is None:
        return PB2AnyValue()
    if isinstance(value, bool):
        return PB2AnyValue(bool_value=value)
    if isinstance(value, int):
        return PB2AnyValue(int_value=value)
    if isinstance(value, float):
        return PB2AnyValue(double_value=value)
    if isinstance(value, str):
        return PB2AnyValue(string_value=value)
    if isinstance(value, bytes):
        return PB2AnyValue(bytes_value=value)
    # TODO: handle sequence and mapping?
    raise ValueError(f"Invalid type {type(value)} of value {value}")


def _encode_attributes(attributes: Mapping[str, AnyValue]):
    return [
        PB2KeyValue(key=key, value=_encode_value(value))
        for key, value in attributes.items()
    ]


def _build_agent_description(
    identifying_attributes: Mapping[str, AnyValue],
    non_identifying_attributes: Mapping[str, AnyValue] | None = None,
) -> opamp_pb2.AgentDescription:
    identifying_attrs = _encode_attributes(identifying_attributes)
    non_identifying_attrs = (
        _encode_attributes(non_identifying_attributes)
        if non_identifying_attributes
        else None
    )
    return opamp_pb2.AgentDescription(
        identifying_attributes=identifying_attrs,
        non_identifying_attributes=non_identifying_attrs,
    )


def _build_presentation_message(
    instance_uid: bytes,
    sequence_num: int,
    agent_description: opamp_pb2.AgentDescription,
    capabilities: int,
) -> opamp_pb2.AgentToServer:
    command = opamp_pb2.AgentToServer(
        instance_uid=instance_uid,
        sequence_num=sequence_num,
        agent_description=agent_description,
        capabilities=capabilities,
    )
    return command


def _build_heartbeat_message(
    instance_uid: bytes, sequence_num: int, capabilities: int
) -> opamp_pb2.AgentToServer:
    command = opamp_pb2.AgentToServer(
        instance_uid=instance_uid,
        sequence_num=sequence_num,
        capabilities=capabilities,
    )
    return command


def _build_agent_disconnect_message(
    instance_uid: bytes, sequence_num: int, capabilities: int
) -> opamp_pb2.AgentToServer:
    command = opamp_pb2.AgentToServer(
        instance_uid=instance_uid,
        sequence_num=sequence_num,
        agent_disconnect=opamp_pb2.AgentDisconnect(),
        capabilities=capabilities,
    )
    return command


def _build_remote_config_status_message(
    last_remote_config_hash: bytes,
    status: opamp_pb2.RemoteConfigStatuses.ValueType,
    error_message: str = "",
) -> opamp_pb2.RemoteConfigStatus:
    return opamp_pb2.RemoteConfigStatus(
        last_remote_config_hash=last_remote_config_hash,
        status=status,
        error_message=error_message,
    )


def _build_remote_config_status_response_message(
    instance_uid: bytes,
    sequence_num: int,
    capabilities: int,
    remote_config_status: opamp_pb2.RemoteConfigStatus,
) -> opamp_pb2.AgentToServer:
    command = opamp_pb2.AgentToServer(
        instance_uid=instance_uid,
        sequence_num=sequence_num,
        remote_config_status=remote_config_status,
        capabilities=capabilities,
    )
    return command


def _encode_message(data: opamp_pb2.AgentToServer) -> bytes:
    return data.SerializeToString()


def _decode_remote_config(
    remote_config: opamp_pb2.AgentRemoteConfig,
) -> Generator[tuple[str, Mapping[str, AnyValue]]]:
    for (
        config_file_name,
        config_file,
    ) in remote_config.config.config_map.items():
        if config_file.content_type in ("application/json", "text/json"):
            try:
                body = config_file.body.decode()
                config_data = json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OpAMPRemoteConfigDecodeException(
                    f"Failed to decode {config_file} with content type {config_file.content_type}: {exc}"
                )

            yield config_file_name, config_data
        else:
            raise OpAMPRemoteConfigParseException(
                f"Cannot parse {config_file_name} with content type {config_file.content_type}"
            )
