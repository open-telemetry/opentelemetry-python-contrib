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

"""
OpenTelemetry Python - OpAMP client
-----------------------------------

This package provides a bunch of classes that can be used by OpenTelemetry distributions implementors
to implement remote config support via the `OpAMP protocol`_.

The client implements the following capabilities:

* ReportsStatus
* ReportsHeartbeat
* AcceptsRemoteConfig
* ReportsRemoteConfig

These capabilities are enough to get a remote config from an opamp server, parse it, apply it and ack it.

While the client supports pluggable transports, only an HTTP backends using the ``requests`` library is
implemented. Adding WebSocket support shouldn't be hard but it will require some rework in the OpAMPAgent
class.

Since OpAMP APIs, config options or environment variables are not standardizes the distros are required
to provide code doing so.
OTel Python distros would need to provide their own message handler callback that implements the actual
change of whatever configuration their backends sends.

Please note that the API is not finalized yet and so the name is called ``_opamp`` with the underscore.

Usage
-----

.. code-block:: python

    import os

    from opentelemetry._opamp import messages
    from opentelemetry._opamp.agent import OpAMPAgent
    from opentelemetry._opamp.client import OpAMPClient
    from opentelemetry._opamp.proto import opamp_pb2 as opamp_pb2
    from opentelemetry.sdk._configuration import _OTelSDKConfigurator
    from opentelemetry.sdk.resources import OTELResourceDetector


    def opamp_handler(agent: OpAMPAgent, client: OpAMPClient, message: opamp_pb2.ServerToAgent):
        for config_filename, config in messages._decode_remote_config(message.remote_config):
            print("do something")


    class MyOpenTelemetryConfigurator(_OTelSDKConfigurator):
        def _configure(self, **kwargs):
            super()._configure(**kwargs)

            enable_opamp = False
            endpoint = os.environ.get("OTEL_PYTHON_OPAMP_ENDPOINT")
            if endpoint:
                # this is not great but we don't have the calculated resource attributes around
                # see https://github.com/open-telemetry/opentelemetry-python/pull/4646 for creating
                # an entry point distros can implement
                resource = OTELResourceDetector().detect()
                agent_identifying_attributes = {
                    "service.name": resource.attributes.get("service.name"),
                }
                opamp_client = OpAMPClient(
                    endpoint=endpoint,
                    agent_identifying_attributes=agent_identifying_attributes,
                )
                opamp_agent = OpAMPAgent(
                    interval=30,
                    message_handler=opamp_handler,
                    client=opamp_client,
                )
                opamp_agent.start()

API
---
.. _OpAMP protocol: https://opentelemetry.io/docs/specs/opamp/
"""

from opentelemetry._opamp.agent import OpAMPAgent
from opentelemetry._opamp.client import OpAMPClient

__all__ = ["OpAMPAgent", "OpAMPClient"]
