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

from logging import getLogger
from typing import Generator, Mapping

from uuid_utils import uuid7

from opentelemetry._opamp import messages
from opentelemetry._opamp.proto import opamp_pb2
from opentelemetry._opamp.transport.requests import RequestsTransport
from opentelemetry._opamp.version import __version__
from opentelemetry.util.types import AnyValue

_logger = getLogger(__name__)

_DEFAULT_OPAMP_TIMEOUT_MS = 1_000

_OTLP_HTTP_HEADERS = {
    "Content-Type": "application/x-protobuf",
    "User-Agent": "OTel-OpAMP-Python/" + __version__,
}

_HANDLED_CAPABILITIES = (
    opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsStatus
    | opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsHeartbeat
    | opamp_pb2.AgentCapabilities.AgentCapabilities_AcceptsRemoteConfig
    | opamp_pb2.AgentCapabilities.AgentCapabilities_ReportsRemoteConfig
)


class OpAMPClient:
    def __init__(
        self,
        *,
        endpoint: str,
        headers: Mapping[str, str] | None = None,
        timeout_millis: int = _DEFAULT_OPAMP_TIMEOUT_MS,
        agent_identifying_attributes: Mapping[str, AnyValue],
        agent_non_identifying_attributes: Mapping[str, AnyValue] | None = None,
    ):
        self._timeout_millis = timeout_millis
        self._transport = RequestsTransport()

        self._endpoint = endpoint
        headers = headers or {}
        self._headers = {**_OTLP_HTTP_HEADERS, **headers}

        self._agent_description = messages._build_agent_description(
            identifying_attributes=agent_identifying_attributes,
            non_identifying_attributes=agent_non_identifying_attributes,
        )
        self._sequence_num: int = 0
        self._instance_uid: bytes = uuid7().bytes
        self._remote_config_status: opamp_pb2.RemoteConfigStatus | None = None

    def _build_connection_message(self) -> bytes:
        message = messages._build_presentation_message(
            instance_uid=self._instance_uid,
            agent_description=self._agent_description,
            sequence_num=self._sequence_num,
            capabilities=_HANDLED_CAPABILITIES,
        )
        data = messages._encode_message(message)
        return data

    def _build_agent_disconnect_message(self) -> bytes:
        message = messages._build_agent_disconnect_message(
            instance_uid=self._instance_uid,
            sequence_num=self._sequence_num,
            capabilities=_HANDLED_CAPABILITIES,
        )
        data = messages._encode_message(message)
        return data

    def _build_heartbeat_message(self) -> bytes:
        message = messages._build_heartbeat_message(
            instance_uid=self._instance_uid,
            sequence_num=self._sequence_num,
            capabilities=_HANDLED_CAPABILITIES,
        )
        data = messages._encode_message(message)
        return data

    def _update_remote_config_status(
        self,
        remote_config_hash: bytes,
        status: opamp_pb2.RemoteConfigStatuses.ValueType,
        error_message: str = "",
    ) -> opamp_pb2.RemoteConfigStatus | None:
        status_changed = (
            not self._remote_config_status
            or self._remote_config_status.last_remote_config_hash
            != remote_config_hash
            or self._remote_config_status.status != status
            or self._remote_config_status.error_message != error_message
        )
        # if the status changed update we return the RemoteConfigStatus message so that we can send it to the server
        if status_changed:
            _logger.debug(
                "Update remote config status changed for %s",
                remote_config_hash,
            )
            self._remote_config_status = (
                messages._build_remote_config_status_message(
                    last_remote_config_hash=remote_config_hash,
                    status=status,
                    error_message=error_message,
                )
            )
            return self._remote_config_status

        return None

    def _build_remote_config_status_response_message(
        self, remote_config_status: opamp_pb2.RemoteConfigStatus
    ) -> bytes:
        message = messages._build_remote_config_status_response_message(
            instance_uid=self._instance_uid,
            sequence_num=self._sequence_num,
            capabilities=_HANDLED_CAPABILITIES,
            remote_config_status=remote_config_status,
        )
        data = messages._encode_message(message)
        return data

    def _send(self, data: bytes):
        try:
            response = self._transport.send(
                url=self._endpoint,
                headers=self._headers,
                data=data,
                timeout_millis=self._timeout_millis,
            )
            return response
        finally:
            self._sequence_num += 1

    @staticmethod
    def _decode_remote_config(
        remote_config: opamp_pb2.AgentRemoteConfig,
    ) -> Generator[tuple[str, Mapping[str, AnyValue]]]:
        for config_file, config in messages._decode_remote_config(
            remote_config
        ):
            yield config_file, config
