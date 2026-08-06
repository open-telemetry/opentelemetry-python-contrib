# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
from time import sleep
from unittest import mock

import pytest

from opentelemetry._opamp.agent import OpAMPAgent
from opentelemetry._opamp.callbacks import OpAMPCallbacks
from opentelemetry._opamp.client import OpAMPClient
from opentelemetry._opamp.proto import opamp_pb2


@pytest.mark.vcr()
def test_connection_remote_config_status_heartbeat_disconnection(caplog):
    caplog.set_level(logging.DEBUG, logger="opentelemetry._opamp.agent")

    class E2ECallbacks(OpAMPCallbacks):
        def on_message(self, agent, client, message):
            logger = logging.getLogger(
                "opentelemetry._opamp.agent.opamp_handler"
            )

            logger.debug("In opamp_handler")

            # we need to update the config only if we have a config
            if (
                message.remote_config is None
                or not message.remote_config.config_hash
            ):
                return

            updated_remote_config = client.update_remote_config_status(
                remote_config_hash=message.remote_config.config_hash,
                status=opamp_pb2.RemoteConfigStatuses_APPLIED,
                error_message="",
            )
            if updated_remote_config is not None:
                logger.debug("Updated Remote Config")
                msg = client.build_remote_config_status_response_message(
                    updated_remote_config
                )
                agent.send(payload=msg)

    opamp_client = OpAMPClient(
        endpoint="https://localhost:4320/v1/opamp",
        agent_identifying_attributes={
            "service.name": "foo",
            "deployment.environment.name": "foo",
        },
        tls_certificate=False,
    )
    opamp_agent = OpAMPAgent(
        interval=1,
        callbacks=E2ECallbacks(),
        client=opamp_client,
    )
    opamp_agent.start()

    # this should be enough for the heartbeat message to be sent
    sleep(1.5)

    opamp_agent.stop()

    handler_records = [
        record[2]
        for record in caplog.record_tuples
        if record[0] == "opentelemetry._opamp.agent.opamp_handler"
    ]
    # connection response has ReportFullState flag, triggering a full state send.
    # on_message is called for: connection, full state response, config status response, heartbeat.
    assert handler_records == [
        "In opamp_handler",
        "Updated Remote Config",
        "In opamp_handler",
        "In opamp_handler",
        "In opamp_handler",
    ]


@pytest.mark.vcr()
def test_with_server_not_responding(caplog):
    caplog.set_level(logging.DEBUG, logger="opentelemetry._opamp.agent")

    cb = mock.create_autospec(OpAMPCallbacks, instance=True)

    opamp_client = OpAMPClient(
        endpoint="https://localhost:4399/v1/opamp",
        agent_identifying_attributes={
            "service.name": "foo",
            "deployment.environment.name": "foo",
        },
        tls_certificate=False,
    )
    opamp_agent = OpAMPAgent(
        interval=1,
        callbacks=cb,
        client=opamp_client,
    )
    opamp_agent.start()

    opamp_agent.stop()

    assert cb.on_message.call_count == 0
