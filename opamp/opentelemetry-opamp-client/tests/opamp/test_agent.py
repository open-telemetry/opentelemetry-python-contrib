# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import logging
from time import sleep
from unittest import mock

from opentelemetry._opamp.agent import OpAMPAgent, _safe_invoke
from opentelemetry._opamp.agent import _Job as Job
from opentelemetry._opamp.callbacks import MessageData, OpAMPCallbacks
from opentelemetry._opamp.proto import opamp_pb2


class _NoOpCallbacks(OpAMPCallbacks):
    pass


def test_can_instantiate_agent():
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks()
    )
    assert isinstance(agent, OpAMPAgent)


def test_can_start_agent():
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks()
    )
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
    cb.on_message.assert_called_once_with(
        agent, client_mock, MessageData(remote_config=None)
    )


def test_agent_can_call_agent_stop_multiple_times():
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks()
    )
    agent.start()
    agent.stop()
    agent.stop()


def test_agent_can_call_agent_stop_before_start():
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks()
    )
    agent.stop()


def test_agent_send_warns_without_worker_thread(caplog):
    agent = OpAMPAgent(
        interval=30, client=mock.Mock(), callbacks=_NoOpCallbacks()
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
    agent = OpAMPAgent(
        interval=30, client=client_mock, callbacks=OrderTrackingCallbacks()
    )
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
    agent = OpAMPAgent(
        interval=30, client=client_mock, callbacks=OrderTrackingCallbacks()
    )
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


def test_safe_invoke_logs_error(caplog):
    caplog.set_level(logging.ERROR, logger="opentelemetry._opamp.agent")

    def bad_callback():
        raise ValueError("boom")

    _safe_invoke(bad_callback)

    assert any(
        "Error when invoking function 'bad_callback'" in record.message
        for record in caplog.records
    )


def test_safe_invoke_does_not_propagate():
    def bad_callback():
        raise RuntimeError("should not propagate")

    # Should not raise
    _safe_invoke(bad_callback)


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
