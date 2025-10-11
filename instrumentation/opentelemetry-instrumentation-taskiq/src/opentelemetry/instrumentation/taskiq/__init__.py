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
Instrument `taskiq`_ to trace Taskiq applications.

.. _taskiq: https://pypi.org/project/taskiq/

Usage
-----

* Run instrumented task

.. code:: python

    import asyncio

    from opentelemetry.instrumentation.taskiq import TaskiqInstrumentor
    from taskiq import InMemoryBroker, TaskiqEvents, TaskiqState

    broker = InMemoryBroker()

    @broker.on_event(TaskiqEvents.WORKER_STARTUP)
    async def startup(state: TaskiqState) -> None:
        TaskiqInstrumentor().instrument()

    @broker.task
    async def add(x, y):
        return x + y

    async def main():
        await broker.startup()
        await my_task.kiq(1, 2)
        await broker.shutdown()

    if __name__ == "__main__":
        asyncio.run(main())

API
---
"""

import logging
from typing import Any, Collection, Optional, TypeVar
from weakref import WeakSet as _WeakSet

from taskiq import AsyncBroker, TaskiqMessage, TaskiqMiddleware, TaskiqResult
from wrapt import wrap_function_wrapper

from opentelemetry import context as context_api
from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.taskiq import utils
from opentelemetry.instrumentation.taskiq.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import Meter, MeterProvider, get_meter
from opentelemetry.propagate import extract, inject
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import Tracer, TracerProvider
from opentelemetry.trace.status import Status, StatusCode

logger = logging.getLogger(__name__)

T = TypeVar("T")


# Task operations
_TASK_TAG_KEY = "taskiq.action"
_TASK_SEND = "send"
_TASK_EXECUTE = "execute"


_TASK_RETRY_REASON_KEY = "taskiq.retry.reason"
_TASK_NAME_KEY = "taskiq.task_name"


class OpenTelemetryMiddleware(TaskiqMiddleware):
    """Middleware to instrument Taskiq with OpenTelemetry."""

    def __init__(
        self,
        tracer_provider: Optional[TracerProvider] = None,
        meter_provider: Optional[MeterProvider] = None,
        tracer: Optional[Tracer] = None,
        meter: Optional[Meter] = None,
    ):
        super().__init__()
        self._tracer = (
            trace.get_tracer(
                __name__,
                __version__,
                tracer_provider,
                schema_url="https://opentelemetry.io/schemas/1.11.0",
            )
            if tracer is None
            else tracer
        )
        self._meter = (
            get_meter(
                __name__,
                __version__,
                meter_provider,
                schema_url="https://opentelemetry.io/schemas/1.11.0",
            )
            if meter is None
            else meter
        )

    def pre_send(self, message: TaskiqMessage) -> TaskiqMessage:
        """Called before sending a task."""
        logger.debug("pre_send task_id=%s", message.task_id)

        operation_name = f"{_TASK_SEND}/{message.task_name}"
        span = self._tracer.start_span(
            operation_name, kind=trace.SpanKind.PRODUCER
        )

        if span.is_recording():
            span.set_attribute(_TASK_TAG_KEY, _TASK_SEND)
            span.set_attribute(
                SpanAttributes.MESSAGING_MESSAGE_ID, message.task_id
            )
            span.set_attribute(_TASK_NAME_KEY, message.task_name)
            utils.set_attributes_from_context(span, message.labels)

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()  # pylint: disable=E1101

        utils.attach_context(message, span, activation, None, is_publish=True)
        inject(message.labels)

        return message

    def post_send(self, message: TaskiqMessage) -> None:  # pylint: disable=R6301
        logger.debug("post_send task_id=%s", message.task_id)
        # retrieve and finish the Span
        ctx = utils.retrieve_context(message, is_publish=True)

        if ctx is None:
            logger.warning(
                "no existing span found for task_id=%s", message.task_id
            )
            return

        _, activation, _ = ctx

        activation.__exit__(None, None, None)  # pylint: disable=E1101
        utils.detach_context(message, is_publish=True)

    def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        logger.debug("pre_execute task_id=%s", message.task_id)
        tracectx = extract(message.labels) or None
        token = context_api.attach(tracectx) if tracectx is not None else None

        operation_name = f"{_TASK_EXECUTE}/{message.task_name}"
        span = self._tracer.start_span(
            operation_name, context=tracectx, kind=trace.SpanKind.CONSUMER
        )

        activation = trace.use_span(span, end_on_exit=True)
        activation.__enter__()  # pylint: disable=E1101
        utils.attach_context(message, span, activation, token)
        return message

    def post_execute(  # pylint: disable=R6301
        self, message: TaskiqMessage, result: TaskiqResult[T]
    ) -> None:
        logger.debug("post_execute task_id=%s", message.task_id)

        # retrieve and finish the Span
        ctx = utils.retrieve_context(message)

        if ctx is None:
            logger.warning(
                "no existing span found for task_id=%s", message.task_id
            )
            return

        span, activation, token = ctx

        if span.is_recording():
            span.set_attribute(_TASK_TAG_KEY, _TASK_EXECUTE)
            utils.set_attributes_from_context(span, message.labels)
            span.set_attribute(_TASK_NAME_KEY, message.task_name)

        activation.__exit__(None, None, None)
        utils.detach_context(message)
        # if the process sending the task is not instrumented
        # there's no incoming context and no token to detach
        if token is not None:
            context_api.detach(token)

    def on_error(  # pylint: disable=R6301
        self,
        message: TaskiqMessage,
        result: TaskiqResult[T],
        exception: BaseException,
    ) -> None:
        ctx = utils.retrieve_context(message)

        if ctx is None:
            return

        span, _, _ = ctx

        if not span.is_recording():
            return

        retry_on_error = message.labels.get("retry_on_error")
        if isinstance(retry_on_error, str):
            retry_on_error = retry_on_error.lower() == "true"

        if retry_on_error is None:
            retry_on_error = False

        if retry_on_error:
            # Add retry reason metadata to span
            span.set_attribute(_TASK_RETRY_REASON_KEY, str(exception))
            return

        status_kwargs = {
            "status_code": StatusCode.ERROR,
            "description": str(exception),
        }
        span.record_exception(exception)
        span.set_status(Status(**status_kwargs))


class TaskiqInstrumentor(BaseInstrumentor):
    """OpenTelemetry instrumentor for Taskiq."""

    _instrumented_brokers: _WeakSet[AsyncBroker] = _WeakSet()

    def __init__(self):
        super().__init__()
        self._middleware = None

    def instrument_broker(
        self,
        broker: AsyncBroker,
        tracer_provider: Optional[TracerProvider] = None,
        meter_provider: Optional[MeterProvider] = None,
    ):
        if not hasattr(broker, "_is_instrumented_by_opentelemetry"):
            broker._is_instrumented_by_opentelemetry = False

        if not getattr(broker, "is_instrumented_by_opentelemetry", False):
            broker.middlewares.insert(
                0,
                OpenTelemetryMiddleware(
                    tracer_provider=tracer_provider,
                    meter_provider=meter_provider,
                ),
            )
            broker._is_instrumented_by_opentelemetry = True
            if broker not in self._instrumented_brokers:
                self._instrumented_brokers.add(broker)
        else:
            logger.warning(
                "Attempting to instrument taskiq broker while already instrumented"
            )

    def uninstrument_broker(self, broker: AsyncBroker):
        broker.middlewares = [
            middleware
            for middleware in broker.middlewares
            if not isinstance(middleware, OpenTelemetryMiddleware)
        ]
        broker._is_instrumented_by_opentelemetry = False
        self._instrumented_brokers.discard(broker)

    def instrumentation_dependencies(self) -> Collection[str]:
        return ("taskiq >= 0.0.1",)

    def _instrument(self, **kwargs: Any):
        def broker_init(init, broker, args, kwargs):
            result = init(*args, **kwargs)
            self.instrument_broker(broker)
            return result

        wrap_function_wrapper("taskiq", "AsyncBroker.__init__", broker_init)

    def _uninstrument(self, **kwargs):
        instances_to_uninstrument = list(self._instrumented_brokers)
        for broker in instances_to_uninstrument:
            self.uninstrument_broker(broker)
        self._instrumented_brokers.clear()
        unwrap(AsyncBroker, "__init__")
