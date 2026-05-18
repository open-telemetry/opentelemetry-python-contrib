# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
OpenTelemetry Python - OpAMP client
-----------------------------------

This package provides a bunch of classes that can be used by OpenTelemetry distributions implementers
to implement remote config support via the `OpAMP protocol`_.

The client implements the following capabilities:

* ReportsStatus
* ReportsHeartbeat
* AcceptsRemoteConfig
* ReportsRemoteConfig
* ReportsEffectiveConfig

These capabilities are enough to get a remote config from an OpAMP server, parse it, apply it and ack it.

While the client supports pluggable transports, only an HTTP backends using the ``requests`` library is
implemented. Adding WebSocket support shouldn't be hard but it will require some rework in the OpAMPAgent
class.

Since OpAMP APIs, config options or environment variables are not standardizes the distros are required
to provide code doing so.
OTel Python distros would need to provide their own OpAMPCallbacks subclass that implements the actual
change of whatever configuration their backends sends.

Please note that the API is not finalized yet and so the name is called ``_opamp`` with the underscore.

Usage
-----

.. code-block:: python

    import os

    from opentelemetry._opamp.agent import OpAMPAgent
    from opentelemetry._opamp.callbacks import OpAMPCallbacks
    from opentelemetry._opamp.client import OpAMPClient
    from opentelemetry.sdk._configuration import _OTelSDKConfigurator
    from opentelemetry.sdk.resources import OTELResourceDetector


    class MyCallbacks(OpAMPCallbacks):
        def on_message(self, agent, client, message):
            if message.remote_config is None:
                return
            for config_filename, config in message.remote_config.config.config_map.items():
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
                    callbacks=MyCallbacks(),
                    client=opamp_client,
                )
                opamp_agent.start()

API
---
.. _OpAMP protocol: https://opentelemetry.io/docs/specs/opamp/
"""

from opentelemetry._opamp.agent import OpAMPAgent
from opentelemetry._opamp.callbacks import MessageData, OpAMPCallbacks
from opentelemetry._opamp.client import OpAMPClient

__all__ = ["MessageData", "OpAMPAgent", "OpAMPCallbacks", "OpAMPClient"]
