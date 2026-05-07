# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import atexit
import logging
import queue
import random
import threading
from typing import Any, Callable

from opentelemetry._opamp.callbacks import MessageData, OpAMPCallbacks
from opentelemetry._opamp.client import OpAMPClient
from opentelemetry._opamp.proto import opamp_pb2

logger = logging.getLogger(__name__)


def _safe_invoke(function: Callable[..., Any], *args: Any) -> None:
    function_name = "<unknown>"
    try:
        function_name = function.__name__
        function(*args)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error(
            "Error when invoking function '%s'", function_name, exc_info=exc
        )


class _Job:
    """
    Represents a single request job, with retry/backoff metadata.
    """

    def __init__(
        self,
        payload: Any,
        max_retries: int = 1,
        initial_backoff: float = 1.0,
        callback: Callable[..., None] | None = None,
    ):
        self.payload = payload
        self.attempt = 0
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        # callback is called after OpAMP message handler is executed
        self.callback = callback

    def should_retry(self) -> bool:
        """Checks if we should retry again"""
        return self.attempt <= self.max_retries

    def delay(self) -> float:
        """Calculate the delay before next retry"""
        assert self.attempt > 0
        return (
            self.initial_backoff
            * (2 ** (self.attempt - 1))
            * random.uniform(0.8, 1.2)
        )


class OpAMPAgent:
    """
    OpAMPAgent handles:
      - periodic “heartbeat” calls enqueued at a fixed interval
      - on-demand calls via send()
      - exponential backoff retry on failures
      - immediate cancellation of all jobs on shutdown
    """

    def __init__(
        self,
        *,
        interval: float = 30,
        callbacks: OpAMPCallbacks,
        max_retries: int = 10,
        heartbeat_max_retries: int = 1,
        initial_backoff: float = 1.0,
        client: OpAMPClient,
    ):
        """
        :param interval: seconds between heartbeat calls
        :param callbacks: OpAMPCallbacks instance for receiving client events
        :param max_retries: how many times to retry a failed job for ad-hoc messages
        :param heartbeat_max_retries: how many times to retry an heartbeat failed job
        :param initial_backoff: base seconds for exponential backoff
        :param client: an OpAMPClient instance
        """
        self._interval = interval
        self._callbacks = callbacks
        self._max_retries = max_retries
        self._heartbeat_max_retries = heartbeat_max_retries
        self._initial_backoff = initial_backoff

        self._queue: queue.Queue[_Job] = queue.Queue()
        self._stop = threading.Event()

        self._worker = threading.Thread(
            name="OpAMPAgentWorker", target=self._run_worker, daemon=True
        )
        self._scheduler = threading.Thread(
            name="OpAMPAgentScheduler", target=self._run_scheduler, daemon=True
        )
        # start scheduling only after connection with server has been established
        self._schedule = False

        self._client = client

    def _enable_scheduler(self):
        self._schedule = True
        logger.debug("Connected with endpoint, enabling heartbeat")

    def start(self) -> None:
        """
        Starts the scheduler and worker threads.
        """
        self._stop.clear()
        self._worker.start()
        self._scheduler.start()

        atexit.register(self.stop)

        # enqueue the connection message so we can then enable heartbeat
        payload = self._client.build_full_state_message()
        self.send(
            payload,
            max_retries=self._max_retries,
            callback=self._enable_scheduler,
        )

    def send(
        self,
        payload: Any,
        max_retries: int | None = None,
        callback: Callable[..., None] | None = None,
    ) -> None:
        """
        Enqueue an on-demand request.
        """
        if not self._worker.is_alive():
            logger.warning(
                "Called send() but worker thread is not alive. Worker threads is started with start()"
            )

        if max_retries is None:
            max_retries = self._max_retries
        job = _Job(
            payload,
            max_retries=max_retries,
            initial_backoff=self._initial_backoff,
            callback=callback,
        )
        self._queue.put(job)
        logger.debug("On-demand job enqueued: %r", payload)

    def _run_scheduler(self) -> None:
        """
        After we made a connection, periodically enqueue “heartbeat” jobs until stop is signaled.
        """
        while not self._stop.wait(self._interval):
            if self._schedule:
                payload = self._client.build_heartbeat_message()
                job = _Job(
                    payload=payload,
                    max_retries=self._heartbeat_max_retries,
                    initial_backoff=self._initial_backoff,
                )
                self._queue.put(job)
                logger.debug("Periodic job enqueued")

    def _run_worker(self) -> None:
        """
        Worker loop: pull jobs, attempt the message handler, retry on failure with backoff.
        """
        # pylint: disable=broad-exception-caught
        while not self._stop.is_set():
            try:
                job: _Job = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            message = None
            while job.should_retry() and not self._stop.is_set():
                try:
                    message = self._client.send(job.payload)
                    _safe_invoke(
                        self._callbacks.on_connect, self, self._client
                    )
                    logger.debug("Job succeeded: %r", job.payload)
                    break
                except Exception as exc:
                    job.attempt += 1
                    _safe_invoke(
                        self._callbacks.on_connect_failed,
                        self,
                        self._client,
                        exc,
                    )
                    logger.warning(
                        "Job %r failed attempt %d/%d: %s",
                        job.payload,
                        job.attempt,
                        job.max_retries + 1,
                        exc,
                    )

                    if not job.should_retry():
                        logger.error(
                            "Job %r dropped after max retries", job.payload
                        )
                        break

                    # exponential backoff with +/- 20% jitter, interruptible by stop event
                    delay = job.delay()
                    logger.debug("Retrying in %.1fs", delay)
                    if self._stop.wait(delay):
                        # stop requested during backoff: abandon job
                        logger.debug(
                            "Stop signaled, abandoning job %r", job.payload
                        )
                        break

            if message is not None:
                self._process_message(message)

            try:
                if job.callback is not None:
                    job.callback()
            except Exception as exc:
                logging.warning("Callback for job failed: %s", exc)
            finally:
                self._queue.task_done()

    def _process_message(self, message: opamp_pb2.ServerToAgent) -> None:
        if message.HasField("error_response"):
            _safe_invoke(
                self._callbacks.on_error,
                self,
                self._client,
                message.error_response,
            )
            return

        if message.flags & opamp_pb2.ServerToAgentFlags_ReportFullState:
            logger.debug("Server requested full state report")
            payload = self._client.build_full_state_message()
            self.send(payload)

        msg_data = MessageData.from_server_message(message)
        _safe_invoke(
            self._callbacks.on_message,
            self,
            self._client,
            msg_data,
        )

    def stop(self, timeout: float | None = None) -> None:
        """
        Signal server we are disconnecting and then threads to exit

        :param timeout: seconds to wait for each thread to join
        """

        # Before exiting send signal the server we are disconnecting to free our resources
        # This is not required by the spec but is helpful in practice
        logger.debug("Stopping OpAMPAgent: sending AgentDisconnect")
        payload = self._client.build_agent_disconnect_message()
        try:
            self._client.send(payload)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug(
                "Stopping OpAMPAgent: failed to send AgentDisconnect message"
            )

        logger.debug("Stopping OpAMPAgent: signaling threads")
        # Signal threads to exit
        self._stop.set()
        # don't crash if the user calls stop() before start() or calls stop() multiple times
        try:
            self._worker.join(timeout=timeout)
        except RuntimeError as exc:
            logger.warning(
                "Stopping OpAMPAgent: worker thread failed to join %s", exc
            )
        try:
            self._scheduler.join(timeout=timeout)
        except RuntimeError as exc:
            logger.warning(
                "Stopping OpAMPAgent: scheduler thread failed to join %s", exc
            )
        logger.debug("OpAMPAgent stopped")
