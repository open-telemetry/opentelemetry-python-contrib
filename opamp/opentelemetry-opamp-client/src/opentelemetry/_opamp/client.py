# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading
from collections.abc import Generator, Mapping
from logging import getLogger
from typing import Any, Final

from uuid_utils import uuid7

from opentelemetry._opamp import messages
from opentelemetry._opamp.proto import opamp_pb2
from opentelemetry._opamp.transport.base import HttpTransport
from opentelemetry._opamp.transport.requests import RequestsTransport
from opentelemetry._opamp.version import __version__
from opentelemetry.context import (
    _SUPPRESS_INSTRUMENTATION_KEY,
    attach,
    detach,
    set_value,
)
from opentelemetry.util.types import AnyValue

_logger = getLogger(__name__)

_DEFAULT_OPAMP_TIMEOUT_MS = 1_000

_OPAMP_HTTP_HEADERS = {
    "Content-Type": "application/x-protobuf",
    "User-Agent": "OTel-OpAMP-Python/" + __version__,
}

_DEFAULT_CAPABILITIES: Final = (
    opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsStatus
    | opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsHeartbeat
    | opamp_pb2.AgentCapabilities.AgentCapabilities_AcceptsRemoteConfig
    | opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsRemoteConfig
    | opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsEffectiveConfig
)


class OpAMPClient:
    """
    OpAMPClient implement the helpers for building and sending messages that the agent will use.

    The build_*_message methods return messages to pass to OpAMPAgent.send() or send(). Their
    instance UID and sequence number are set when they are sent, by prepare_message().
    """

    def __init__(
        self,
        *,
        endpoint: str,
        headers: Mapping[str, str] | None = None,
        timeout_millis: int = _DEFAULT_OPAMP_TIMEOUT_MS,
        agent_identifying_attributes: Mapping[str, AnyValue],
        agent_non_identifying_attributes: Mapping[str, AnyValue] | None = None,
        capabilities: int = _DEFAULT_CAPABILITIES,
        transport: HttpTransport | None = None,
        # this matches requests but can be mapped to other http libraries APIs
        tls_certificate: str | bool = True,
        tls_client_certificate: str | None = None,
        tls_client_key: str | None = None,
    ):
        # ReportsStatus is required by the OpAMP specification:
        # https://opentelemetry.io/docs/specs/opamp/#agenttoservercapabilities
        if not capabilities & (opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsStatus):
            raise ValueError("OpAMP capabilities must include ReportsStatus")

        self._capabilities = capabilities
        self._timeout_millis = timeout_millis
        self._transport = RequestsTransport() if transport is None else transport

        self._endpoint = endpoint
        headers = headers or {}
        self._headers = {**_OPAMP_HTTP_HEADERS, **headers}
        self._tls_certificate = tls_certificate
        self._tls_client_certificate = tls_client_certificate
        self._tls_client_key = tls_client_key

        self._agent_description = messages.build_agent_description(
            identifying_attributes=agent_identifying_attributes,
            non_identifying_attributes=agent_non_identifying_attributes,
        )
        self._sequence_num: int = 0
        self._sequence_num_lock = threading.Lock()
        self._instance_uid: bytes = uuid7().bytes
        self._remote_config_status: opamp_pb2.RemoteConfigStatus | None = None
        self._effective_config: opamp_pb2.EffectiveConfig | None = None

    def prepare_message(self, message: opamp_pb2.AgentToServer | bytes) -> bytes:
        """
        Returns the message encoded for sending, with the current instance UID and the next
        sequence number.

        Call it once for each message, right before it is first sent: a message that is sent
        again keeps its sequence number, so the server sees a gap only when a message never
        reached it. Bytes are decoded as an AgentToServer message first. The message passed
        in is not changed.
        """
        prepared = opamp_pb2.AgentToServer()
        if isinstance(message, opamp_pb2.AgentToServer):
            prepared.CopyFrom(message)
        else:
            prepared.ParseFromString(message)
        with self._sequence_num_lock:
            prepared.instance_uid = self._instance_uid
            prepared.sequence_num = self._sequence_num
            self._sequence_num += 1
        return messages.encode_message(prepared)

    def build_agent_disconnect_message(self) -> opamp_pb2.AgentToServer:
        message = messages.build_agent_disconnect_message(
            instance_uid=self._instance_uid,
            sequence_num=self._sequence_num,
            capabilities=self._capabilities,
        )
        return message

    def build_heartbeat_message(self) -> opamp_pb2.AgentToServer:
        message = messages.build_heartbeat_message(
            instance_uid=self._instance_uid,
            sequence_num=self._sequence_num,
            capabilities=self._capabilities,
        )
        return message

    def update_effective_config(
        self,
        effective_config: Mapping[str, Any],
        content_type: str,
    ) -> opamp_pb2.EffectiveConfig:
        self._effective_config = messages.build_effective_config_message(
            config=effective_config, content_type=content_type
        )
        return self._effective_config

    def update_remote_config_status(
        self,
        remote_config_hash: bytes,
        status: opamp_pb2.RemoteConfigStatuses.ValueType,
        error_message: str = "",
    ) -> opamp_pb2.RemoteConfigStatus | None:
        status_changed = (
            not self._remote_config_status
            or self._remote_config_status.last_remote_config_hash != remote_config_hash
            or self._remote_config_status.status != status
            or self._remote_config_status.error_message != error_message
        )
        # if the status changed update we return the RemoteConfigStatus message so that we can send it to the server
        if status_changed:
            _logger.debug(
                "Update remote config status changed for %s",
                remote_config_hash,
            )
            self._remote_config_status = messages.build_remote_config_status_message(
                last_remote_config_hash=remote_config_hash,
                status=status,
                error_message=error_message,
            )
            return self._remote_config_status

        return None

    def build_remote_config_status_response_message(
        self, remote_config_status: opamp_pb2.RemoteConfigStatus
    ) -> opamp_pb2.AgentToServer:
        message = messages.build_remote_config_status_response_message(
            instance_uid=self._instance_uid,
            sequence_num=self._sequence_num,
            capabilities=self._capabilities,
            remote_config_status=remote_config_status,
        )
        return message

    def build_full_state_message(self) -> opamp_pb2.AgentToServer:
        message = messages.build_full_state_message(
            instance_uid=self._instance_uid,
            agent_description=self._agent_description,
            remote_config_status=self._remote_config_status,
            sequence_num=self._sequence_num,
            effective_config=self._effective_config,
            capabilities=self._capabilities,
        )
        return message

    def send(self, data: opamp_pb2.AgentToServer | bytes):
        """
        Sends a message to the server and returns its response.

        A message is prepared first (see prepare_message). Bytes are sent as they are.
        """
        if isinstance(data, opamp_pb2.AgentToServer):
            data = self.prepare_message(data)
        token = attach(set_value(_SUPPRESS_INSTRUMENTATION_KEY, True))
        try:
            response = self._transport.send(
                url=self._endpoint,
                headers=self._headers,
                data=data,
                timeout_millis=self._timeout_millis,
                tls_certificate=self._tls_certificate,
                tls_client_certificate=self._tls_client_certificate,
                tls_client_key=self._tls_client_key,
            )
            return response
        finally:
            detach(token)

    @staticmethod
    def decode_remote_config(
        remote_config: opamp_pb2.AgentRemoteConfig,
    ) -> Generator[tuple[str, Mapping[str, AnyValue]]]:
        for config_file, config in messages.decode_remote_config(remote_config):
            yield config_file, config
