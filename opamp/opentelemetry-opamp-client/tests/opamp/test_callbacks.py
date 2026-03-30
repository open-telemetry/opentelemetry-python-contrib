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
