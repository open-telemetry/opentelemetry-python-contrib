# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from opentelemetry._opamp.callbacks import MessageData, OpAMPCallbacks
from opentelemetry._opamp.proto import opamp_pb2


def test_subclass_override_subset():
    class MyCallbacks(OpAMPCallbacks):
        def __init__(self):
            self.connected = False

        def on_connect(self, agent, client):
            self.connected = True

    cb = MyCallbacks()
    cb.on_connect(mock.Mock(), mock.Mock())
    assert cb.connected is True

    # non-overridden methods still work as no-ops
    cb.on_connect_failed(mock.Mock(), mock.Mock(), Exception())
    cb.on_message(mock.Mock(), mock.Mock(), MessageData())
    cb.on_error(mock.Mock(), mock.Mock(), opamp_pb2.ServerErrorResponse())
