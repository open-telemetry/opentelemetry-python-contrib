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

import logging
from time import sleep
from unittest import mock

from opentelemetry._opamp.agent import OpAMPAgent
from opentelemetry._opamp.agent import _Job as Job


def test_can_instantiate_agent():
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), message_handler=mock.Mock()
    )
    assert isinstance(agent, OpAMPAgent)


def test_can_start_agent():
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), message_handler=mock.Mock()
    )
    agent.start()
    agent.stop()


def test_agent_start_will_send_connection_and_disconnetion_messages():
    client_mock = mock.Mock()
    mock_message = {"mock": "message"}
    client_mock._send.return_value = mock_message
    message_handler = mock.Mock()
    agent = OpAMPAgent(
        interval=30, client=client_mock, message_handler=message_handler
    )
    agent.start()
    # wait for the queue to be consumed
    sleep(0.1)
    agent.stop()

    # one send for connection message, one for disconnect agent message
    assert client_mock._send.call_count == 2
    # connection callback has been called
    assert agent._schedule is True
    # connection message response has been received
    message_handler.assert_called_once_with(agent, client_mock, mock_message)


def test_agent_can_call_agent_stop_multiple_times():
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), message_handler=mock.Mock()
    )
    agent.start()
    agent.stop()
    agent.stop()


def test_agent_can_call_agent_stop_before_start():
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), message_handler=mock.Mock()
    )
    agent.stop()


def test_agent_send_warns_without_worker_thread(caplog):
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), message_handler=mock.Mock()
    )
    agent.send(payload="payload")

    assert caplog.record_tuples == [
        (
            "opentelemetry._opamp.agent",
            logging.WARNING,
            "Called send() but worker thread is not alive. Worker threads is started with start()",
        )
    ]


def test_agent_retries_before_max_attempts(caplog):
    caplog.set_level(logging.DEBUG, logger="opentelemetry._opamp.agent")
    message_handler_mock = mock.Mock()
    client_mock = mock.Mock()
    connection_message = disconnection_message = server_message = mock.Mock()
    client_mock._send.side_effect = [
        connection_message,
        Exception,
        server_message,
        disconnection_message,
    ]
    agent = OpAMPAgent(
        interval=30,
        client=client_mock,
        message_handler=message_handler_mock,
        initial_backoff=0,
    )
    agent.start()
    agent.send(payload="payload")
    # wait for the queue to be consumed
    sleep(0.1)
    agent.stop()

    assert client_mock._send.call_count == 4
    assert message_handler_mock.call_count == 2


def test_agent_stops_after_max_attempts(caplog):
    caplog.set_level(logging.DEBUG, logger="opentelemetry._opamp.agent")
    message_handler_mock = mock.Mock()
    client_mock = mock.Mock()
    connection_message = disconnection_message = mock.Mock()
    client_mock._send.side_effect = [
        connection_message,
        Exception,
        Exception,
        disconnection_message,
    ]
    agent = OpAMPAgent(
        interval=30,
        client=client_mock,
        message_handler=message_handler_mock,
        max_retries=1,
        initial_backoff=0,
    )
    agent.start()
    agent.send(payload="payload")
    # wait for the queue to be consumed
    sleep(0.1)
    agent.stop()

    assert client_mock._send.call_count == 4
    assert message_handler_mock.call_count == 1


def test_agent_send_enqueues_job():
    message_handler_mock = mock.Mock()
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), message_handler=message_handler_mock
    )
    agent.start()
    # wait for the queue to be consumed
    sleep(0.1)
    # message handler called for connection message
    assert message_handler_mock.call_count == 1
    agent.send(payload="payload")
    # wait for the queue to be consumed
    sleep(0.1)
    agent.stop()

    # message handler called once for connection and once for our message
    assert message_handler_mock.call_count == 2


def test_can_instantiate_job():
    job = Job(payload="payload")

    assert isinstance(job, Job)


def test_job_should_retry():
    job = Job(payload="payload")
    assert job.attempt == 0
    assert job.max_retries == 1
    assert job.should_retry() is True

    job.attempt += 1
    assert job.should_retry() is True

    job.attempt += 1
    assert job.should_retry() is False


def test_job_delay():
    job = Job(payload="payload")

    assert job.initial_backoff == 1
    job.attempt = 1
    assert (
        job.initial_backoff * 0.8 <= job.delay() <= job.initial_backoff * 1.2
    )

    job.attempt = 2
    assert (
        2 * job.initial_backoff * 0.8
        <= job.delay()
        <= 2 * job.initial_backoff * 1.2
    )

    job.attempt = 3
    assert (
        (2**2) * job.initial_backoff * 0.8
        <= job.delay()
        <= (2**2) * job.initial_backoff * 1.2
    )


def test_job_delay_has_jitter():
    job = Job(payload="payload")
    job.attempt = 1
    assert len({job.delay() for i in range(10)}) > 1
