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

from abc import ABC
from dataclasses import dataclass
from typing import TYPE_CHECKING

from opentelemetry._opamp.proto import opamp_pb2

if TYPE_CHECKING:
    from opentelemetry._opamp.agent import OpAMPAgent
    from opentelemetry._opamp.client import OpAMPClient


@dataclass
class MessageData:
    """Structured view of a ServerToAgent message for callback consumption.

    Only fields the agent is expected to act on are exposed. Flags and
    error_response are handled internally by the client before this
    object reaches the callback.
    """

    remote_config: opamp_pb2.AgentRemoteConfig | None = None

    @classmethod
    def from_server_message(
        cls, message: opamp_pb2.ServerToAgent
    ) -> MessageData:
        return cls(
            remote_config=message.remote_config
            if message.HasField("remote_config")
            else None,
        )


class Callbacks(ABC):
    """OpAMP client callbacks with no-op defaults.

    All methods have no-op defaults so that subclasses only need to
    override the callbacks they care about. New callbacks can be added
    in the future without breaking existing subclasses.
    """

    def on_connect(self, agent: OpAMPAgent, client: OpAMPClient) -> None:
        """Called when the connection is successfully established to the
        Server. For HTTP clients this is called for any request if the
        response status is OK.
        """

    def on_connect_failed(
        self,
        agent: OpAMPAgent,
        client: OpAMPClient,
        error: Exception,
    ) -> None:
        """Called when the connection to the Server cannot be established.
        May also be called if the connection is lost and reconnection
        attempt fails.
        """

    def on_error(
        self,
        agent: OpAMPAgent,
        client: OpAMPClient,
        error_response: opamp_pb2.ServerErrorResponse,
    ) -> None:
        """Called when the Server reports an error in response to a
        previously sent request. Useful for logging purposes. The Agent
        should not attempt to process the error by reconnecting or
        retrying previous operations. The client handles the UNAVAILABLE
        case internally by performing retries as necessary.
        """

    def on_message(
        self,
        agent: OpAMPAgent,
        client: OpAMPClient,
        message: MessageData,
    ) -> None:
        """Called when the Agent receives a message that needs processing."""
