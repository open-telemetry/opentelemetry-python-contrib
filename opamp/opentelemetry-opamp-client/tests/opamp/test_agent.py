# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
import threading
from time import monotonic, sleep
from unittest import mock

from opentelemetry._opamp.agent import OpAMPAgent, _safe_invoke
from opentelemetry._opamp.agent import _Job as Job
from opentelemetry._opamp.callbacks import MessageData, OpAMPCallbacks
from opentelemetry._opamp.client import OpAMPClient
from opentelemetry._opamp.proto import opamp_pb2
from opentelemetry._opamp.transport.base import HttpTransport


class _NoOpCallbacks(OpAMPCallbacks):
    pass


class _RecordingTransport(HttpTransport):
    """Records every AgentToServer it is given.

    The request numbered ``hold`` (1-based) waits until ``release`` is set, and the one
    numbered ``fail`` raises. ``responses`` are returned in order, then empty messages.
    """

    def __init__(self, hold=None, fail=None, responses=()):
        self.sent = []
        self.hold, self.fail = hold, fail
        self.held = threading.Event()
        self.release = threading.Event()
        self._responses = list(responses)

    def send(
        self, *, url, headers, data, timeout_millis, tls_certificate, tls_client_certificate=None, tls_client_key=None
    ):
        message = opamp_pb2.AgentToServer()
        message.ParseFromString(data)
        self.sent.append(message)
        if len(self.sent) == self.hold:
            self.held.set()
            assert self.release.wait(5)
        if len(self.sent) == self.fail:
            raise ConnectionError("request failed")
        return self._responses.pop(0) if self._responses else opamp_pb2.ServerToAgent()

    def sequence_nums(self):
        return [message.sequence_num for message in self.sent]


def _client(transport):
    return OpAMPClient(
        endpoint="http://localhost/v1/opamp",
        agent_identifying_attributes={"service.name": "test"},
        transport=transport,
    )


def _wait_for(condition, timeout=5.0):
    deadline = monotonic() + timeout
    while not condition():
        assert monotonic() < deadline, "timed out"
        sleep(0.005)


def _wait_until_idle(agent):
    _wait_for(lambda: agent._queue.unfinished_tasks == 0)


def test_can_instantiate_agent():
    agent = OpAMPAgent(interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks())
    assert isinstance(agent, OpAMPAgent)


def test_can_start_agent():
    agent = OpAMPAgent(interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks())
    agent.start()
    agent.stop()


def test_agent_start_will_send_connection_and_disconnetion_messages():
    client_mock = mock.Mock()
    mock_message = mock.Mock()
    mock_message.HasField.return_value = False
    mock_message.flags = 0
    client_mock.send.return_value = mock_message

    cb = mock.create_autospec(OpAMPCallbacks, instance=True)
    agent = OpAMPAgent(interval=30, client=client_mock, callbacks=cb)
    agent.start()
    # wait for the queue to be consumed
    sleep(0.1)
    agent.stop()

    # one send for connection message, one for disconnect agent message
    assert client_mock.send.call_count == 2
    # connection callback has been called
    assert agent._schedule is True
    # on_connect and on_message called for the connection response
    cb.on_connect.assert_called_once_with(agent, client_mock)
    cb.on_message.assert_called_once_with(agent, client_mock, MessageData(remote_config=None))


def test_agent_can_call_agent_stop_multiple_times():
    agent = OpAMPAgent(interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks())
    agent.start()
    agent.stop()
    agent.stop()


def test_agent_can_call_agent_stop_before_start():
    agent = OpAMPAgent(interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks())
    agent.stop()


def test_agent_send_warns_without_worker_thread(caplog):
    agent = OpAMPAgent(interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks())
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

    cb = mock.create_autospec(OpAMPCallbacks, instance=True)
    client_mock = mock.Mock()
    connection_message = mock.Mock()
    connection_message.HasField.return_value = False
    connection_message.flags = 0
    server_message = mock.Mock()
    server_message.HasField.return_value = False
    server_message.flags = 0
    disconnection_message = mock.Mock()
    client_mock.send.side_effect = [
        connection_message,
        Exception("fail"),
        server_message,
        disconnection_message,
    ]
    agent = OpAMPAgent(
        interval=30,
        client=client_mock,
        callbacks=cb,
        initial_backoff=0,
    )
    agent.start()
    agent.send(payload="payload")
    # wait for the queue to be consumed
    sleep(0.1)
    agent.stop()

    assert client_mock.send.call_count == 4
    assert cb.on_message.call_count == 2
    assert cb.on_connect.call_count == 2
    assert cb.on_connect_failed.call_count == 1


def test_agent_stops_after_max_attempts(caplog):
    caplog.set_level(logging.DEBUG, logger="opentelemetry._opamp.agent")

    cb = mock.create_autospec(OpAMPCallbacks, instance=True)
    client_mock = mock.Mock()
    connection_message = mock.Mock()
    connection_message.HasField.return_value = False
    connection_message.flags = 0
    disconnection_message = mock.Mock()
    exc1 = Exception("fail1")
    exc2 = Exception("fail2")
    client_mock.send.side_effect = [
        connection_message,
        exc1,
        exc2,
        disconnection_message,
    ]
    agent = OpAMPAgent(
        interval=30,
        client=client_mock,
        callbacks=cb,
        max_retries=1,
        initial_backoff=0,
    )
    agent.start()
    agent.send(payload="payload")
    # wait for the queue to be consumed
    sleep(0.1)
    agent.stop()

    assert client_mock.send.call_count == 4
    assert cb.on_message.call_count == 1
    assert cb.on_connect_failed.call_count == 2
    cb.on_connect_failed.assert_any_call(agent, client_mock, exc1)
    cb.on_connect_failed.assert_any_call(agent, client_mock, exc2)


def test_agent_send_enqueues_job():
    cb = mock.create_autospec(OpAMPCallbacks, instance=True)
    client_mock = mock.Mock()
    msg = mock.Mock()
    msg.HasField.return_value = False
    msg.flags = 0
    client_mock.send.return_value = msg

    agent = OpAMPAgent(interval=30, client=client_mock, callbacks=cb)
    agent.start()
    # wait for the queue to be consumed
    sleep(0.1)
    # on_message called for connection message
    assert cb.on_message.call_count == 1
    agent.send(payload="payload")
    # wait for the queue to be consumed
    sleep(0.1)
    agent.stop()

    # on_message called once for connection and once for our message
    assert cb.on_message.call_count == 2


def test_on_error_called_without_on_message_for_error_response():
    cb = mock.create_autospec(OpAMPCallbacks, instance=True)
    client_mock = mock.Mock()

    error_response = opamp_pb2.ServerErrorResponse(
        error_message="server error",
    )
    server_msg = opamp_pb2.ServerToAgent(
        error_response=error_response,
    )
    # connection message (no error)
    conn_msg = opamp_pb2.ServerToAgent()

    client_mock.send.side_effect = [
        conn_msg,  # connection
        server_msg,  # message with error_response
        mock.Mock(),  # disconnect
    ]
    agent = OpAMPAgent(interval=30, client=client_mock, callbacks=cb)
    agent.start()
    agent.send(payload="payload")
    sleep(0.1)
    agent.stop()

    # on_message called only for connection (not for error_response message)
    assert cb.on_message.call_count == 1
    # on_error called for the message with error_response
    cb.on_error.assert_called_once_with(agent, client_mock, error_response)


def test_on_error_not_called_without_error_response():
    cb = mock.create_autospec(OpAMPCallbacks, instance=True)
    client_mock = mock.Mock()

    server_msg = opamp_pb2.ServerToAgent()
    client_mock.send.side_effect = [
        server_msg,  # connection
        server_msg,  # message without error_response
        mock.Mock(),  # disconnect
    ]
    agent = OpAMPAgent(interval=30, client=client_mock, callbacks=cb)
    agent.start()
    agent.send(payload="payload")
    sleep(0.1)
    agent.stop()

    assert cb.on_message.call_count == 2
    cb.on_error.assert_not_called()


def test_dispatch_order_with_error():
    """Verify that error_response skips on_message: on_connect -> on_error."""
    call_order = []
    client_mock = mock.Mock()

    error_response = opamp_pb2.ServerErrorResponse(
        error_message="err",
    )
    server_msg = opamp_pb2.ServerToAgent(
        error_response=error_response,
    )

    class OrderTrackingCallbacks(OpAMPCallbacks):
        def on_connect(self, agent, client):
            call_order.append("on_connect")

        def on_message(self, agent, client, message):
            call_order.append("on_message")

        def on_error(self, agent, client, error_response):
            call_order.append("on_error")

    client_mock.send.side_effect = [
        server_msg,  # connection message with error
        mock.Mock(),  # disconnect
    ]
    agent = OpAMPAgent(interval=30, client=client_mock, callbacks=OrderTrackingCallbacks())
    agent.start()
    sleep(0.1)
    agent.stop()

    assert call_order == ["on_connect", "on_error"]


def test_dispatch_order_without_error():
    """Verify normal dispatch order: on_connect -> on_message."""
    call_order = []
    client_mock = mock.Mock()

    server_msg = opamp_pb2.ServerToAgent()

    class OrderTrackingCallbacks(OpAMPCallbacks):
        def on_connect(self, agent, client):
            call_order.append("on_connect")

        def on_message(self, agent, client, message):
            call_order.append("on_message")

        def on_error(self, agent, client, error_response):
            call_order.append("on_error")

    client_mock.send.side_effect = [
        server_msg,  # connection message, no error
        mock.Mock(),  # disconnect
    ]
    agent = OpAMPAgent(interval=30, client=client_mock, callbacks=OrderTrackingCallbacks())
    agent.start()
    sleep(0.1)
    agent.stop()

    assert call_order == ["on_connect", "on_message"]


def test_report_full_state_flag_triggers_full_state_send():
    cb = mock.create_autospec(OpAMPCallbacks, instance=True)
    client_mock = mock.Mock()

    conn_msg = opamp_pb2.ServerToAgent()
    flag_msg = opamp_pb2.ServerToAgent(
        flags=opamp_pb2.ServerToAgentFlags_ReportFullState,
    )

    no_flag_msg = opamp_pb2.ServerToAgent()
    client_mock.send.side_effect = [
        conn_msg,  # connection
        flag_msg,  # response with ReportFullState
        no_flag_msg,  # full state response
        no_flag_msg,  # disconnect
    ]
    client_mock.build_full_state_message.return_value = b"full-state"

    agent = OpAMPAgent(interval=30, client=client_mock, callbacks=cb)
    agent.start()
    agent.send(payload="payload")
    sleep(0.2)
    agent.stop()

    client_mock.build_full_state_message.assert_called()


def test_heartbeats_queued_behind_a_slow_request_get_consecutive_sequence_nums():
    transport = _RecordingTransport(hold=2)
    agent = OpAMPAgent(interval=0.01, client=_client(transport), callbacks=_NoOpCallbacks())
    agent.start()
    assert transport.held.wait(5)
    # the first heartbeat is in flight: let a few more queue up behind it
    _wait_for(lambda: agent._queue.qsize() >= 2)
    agent._schedule = False
    sleep(0.05)
    transport.release.set()
    _wait_until_idle(agent)
    agent.stop()

    assert len(transport.sent) >= 5
    assert transport.sequence_nums() == list(range(len(transport.sent)))


def test_retried_message_gets_a_new_sequence_num():
    cb = mock.create_autospec(OpAMPCallbacks, instance=True)
    transport = _RecordingTransport(
        fail=2,
        responses=[opamp_pb2.ServerToAgent(flags=opamp_pb2.ServerToAgentFlags_ReportFullState)],
    )
    agent = OpAMPAgent(interval=30, client=_client(transport), callbacks=cb, initial_backoff=0)
    agent.start()
    _wait_for(lambda: len(transport.sent) == 3)
    _wait_until_idle(agent)
    agent.stop()

    # connection, full state report (fails), its retry, disconnect
    assert transport.sequence_nums() == [0, 1, 2, 3]
    assert transport.sent[2].HasField("agent_description")
    assert cb.on_connect_failed.call_count == 1


def test_send_builds_callable_payload_when_sent():
    transport = _RecordingTransport(hold=1)
    client = _client(transport)
    agent = OpAMPAgent(interval=30, client=client, callbacks=_NoOpCallbacks())
    agent.start()
    assert transport.held.wait(5)
    # queued while the connection message is in flight
    agent.send(client.build_heartbeat_message)
    agent.send(client.build_heartbeat_message)
    transport.release.set()
    _wait_until_idle(agent)
    agent.stop()

    assert transport.sequence_nums() == [0, 1, 2, 3]


def test_send_passes_bytes_payload_unchanged():
    client_mock = mock.Mock()
    client_mock.send.return_value = opamp_pb2.ServerToAgent()
    agent = OpAMPAgent(interval=30, client=client_mock, callbacks=_NoOpCallbacks())
    agent.start()
    agent.send(b"prebuilt")
    _wait_until_idle(agent)
    agent.stop()

    client_mock.send.assert_any_call(b"prebuilt")


def test_job_is_dropped_when_its_message_cannot_be_built(caplog):
    cb = mock.create_autospec(OpAMPCallbacks, instance=True)
    transport = _RecordingTransport()
    client = _client(transport)
    agent = OpAMPAgent(interval=30, client=client, callbacks=cb)
    agent.start()

    broken = mock.Mock(side_effect=ValueError("boom"))
    agent.send(broken)
    agent.send(client.build_heartbeat_message)
    _wait_until_idle(agent)
    agent.stop()

    # not retried, and nothing was sent for it: connection, heartbeat, disconnect
    broken.assert_called_once_with()
    assert transport.sequence_nums() == [0, 1, 2]
    cb.on_connect_failed.assert_not_called()
    assert "Failed to build message" in caplog.text


def test_safe_invoke_logs_error(caplog):
    caplog.set_level(logging.ERROR, logger="opentelemetry._opamp.agent")

    def bad_callback():
        raise ValueError("boom")

    _safe_invoke(bad_callback)

    assert any("Error when invoking function 'bad_callback'" in record.message for record in caplog.records)


def test_safe_invoke_does_not_propagate():
    def bad_callback():
        raise RuntimeError("should not propagate")

    # Should not raise
    _safe_invoke(bad_callback)


def test_can_instantiate_job():
    job = Job(payload="payload")

    assert isinstance(job, Job)


def test_job_build_returns_bytes_payload():
    assert Job(payload=b"message").build() == b"message"


def test_job_build_calls_callable_payload_each_time():
    builder = mock.Mock(side_effect=[b"first", b"second"])
    job = Job(payload=builder)

    assert job.build() == b"first"
    assert job.build() == b"second"


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
    assert job.initial_backoff * 0.8 <= job.delay() <= job.initial_backoff * 1.2

    job.attempt = 2
    assert 2 * job.initial_backoff * 0.8 <= job.delay() <= 2 * job.initial_backoff * 1.2

    job.attempt = 3
    assert (2**2) * job.initial_backoff * 0.8 <= job.delay() <= (2**2) * job.initial_backoff * 1.2


def test_job_delay_has_jitter():
    job = Job(payload="payload")
    job.attempt = 1
    assert len({job.delay() for i in range(10)}) > 1
