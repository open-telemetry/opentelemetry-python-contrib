# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=no-name-in-module

from __future__ import annotations

import json
from logging import getLogger
from typing import Any, Generator, Mapping

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

_logger = getLogger(__name__)


def decode_message(data: bytes) -> opamp_pb2.ServerToAgent:
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


def build_agent_description(
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


def build_heartbeat_message(
    instance_uid: bytes, sequence_num: int, capabilities: int
) -> opamp_pb2.AgentToServer:
    command = opamp_pb2.AgentToServer(
        instance_uid=instance_uid,
        sequence_num=sequence_num,
        capabilities=capabilities,
    )
    return command


def build_agent_disconnect_message(
    instance_uid: bytes, sequence_num: int, capabilities: int
) -> opamp_pb2.AgentToServer:
    command = opamp_pb2.AgentToServer(
        instance_uid=instance_uid,
        sequence_num=sequence_num,
        agent_disconnect=opamp_pb2.AgentDisconnect(),
        capabilities=capabilities,
    )
    return command


def build_remote_config_status_message(
    last_remote_config_hash: bytes,
    status: opamp_pb2.RemoteConfigStatuses.ValueType,
    error_message: str = "",
) -> opamp_pb2.RemoteConfigStatus:
    return opamp_pb2.RemoteConfigStatus(
        last_remote_config_hash=last_remote_config_hash,
        status=status,
        error_message=error_message,
    )


def build_remote_config_status_response_message(
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


def build_effective_config_message(
    config: Mapping[str, Any], content_type: str
):
    agent_config_map = opamp_pb2.AgentConfigMap()
    for config_name, config_value in config.items():
        body = encode_effective_config_body(content_type, config_value)
        if body is None:
            _logger.warning(
                "Skipping effective config entry %s with content type %s "
                "because the value cannot be encoded",
                config_name,
                content_type,
            )
            continue

        config_entry = agent_config_map.config_map[config_name]
        config_entry.body = body
        config_entry.content_type = content_type
    return opamp_pb2.EffectiveConfig(
        config_map=agent_config_map,
    )


def encode_effective_config_body(
    content_type: str, value: Any
) -> bytes | None:
    if content_type == "application/json":
        try:
            return json.dumps(value).encode("utf-8")
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, bytes):
        return value
    return None


def build_full_state_message(
    instance_uid: bytes,
    sequence_num: int,
    agent_description: opamp_pb2.AgentDescription,
    capabilities: int,
    remote_config_status: opamp_pb2.RemoteConfigStatus | None,
    effective_config: opamp_pb2.EffectiveConfig | None,
) -> opamp_pb2.AgentToServer:
    command = opamp_pb2.AgentToServer(
        instance_uid=instance_uid,
        sequence_num=sequence_num,
        agent_description=agent_description,
        remote_config_status=remote_config_status,
        effective_config=effective_config,
        capabilities=capabilities,
    )
    return command


def encode_message(data: opamp_pb2.AgentToServer) -> bytes:
    return data.SerializeToString()


def decode_remote_config(
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
                    f"Failed to decode {config_file_name} with content type {config_file.content_type}: {exc}"
                )

            yield config_file_name, config_data
        else:
            raise OpAMPRemoteConfigParseException(
                f"Cannot parse {config_file_name} with content type {config_file.content_type}"
            )
