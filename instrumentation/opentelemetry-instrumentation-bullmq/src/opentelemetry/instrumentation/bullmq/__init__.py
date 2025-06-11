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
Instrument `bullmq`_ to trace BullMQ job queue operations.

.. _bullmq: https://pypi.org/project/bullmq/

Usage
-----

* Start Redis backend

.. code::

    docker run -p 6379:6379 redis


* Run instrumented application

.. code:: python

    from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
    from bullmq import Queue, Worker
    
    # Instrument BullMQ
    BullMQInstrumentor().instrument()
    
    # Create queue and add job
    queue = Queue("myqueue")
    await queue.add("myjob", {"foo": "bar"})
    
    # Create worker to process jobs
    async def process_job(job):
        print(f"Processing job {job.id}: {job.data}")
        return "completed"
    
    worker = Worker("myqueue", process_job)
    await worker.run()

API
---
"""

import logging
from typing import Collection
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation.bullmq.package import _instruments
from opentelemetry.instrumentation.bullmq.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.status import Status, StatusCode

logger = logging.getLogger(__name__)


class BullMQInstrumentor(BaseInstrumentor):
    """An instrumentor for BullMQ"""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments BullMQ library"""
        tracer_provider = kwargs.get("tracer_provider")
        
        # pylint: disable=attribute-defined-outside-init
        self._tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        # Instrument Queue operations
        wrap_function_wrapper(
            "bullmq", "Queue.add", self._trace_queue_add
        )
        wrap_function_wrapper(
            "bullmq", "Queue.add_bulk", self._trace_queue_add_bulk
        )
        
        # Instrument Worker operations
        wrap_function_wrapper(
            "bullmq", "Worker.run", self._trace_worker_run
        )

    def _uninstrument(self, **kwargs):
        """Uninstruments BullMQ library"""
        unwrap("bullmq.Queue", "add")
        unwrap("bullmq.Queue", "add_bulk")
        unwrap("bullmq.Worker", "run")

    def _trace_queue_add(self, wrapped, instance, args, kwargs):
        """Trace Queue.add method"""
        job_name = args[0] if args else kwargs.get("name", "unknown")
        job_data = args[1] if len(args) > 1 else kwargs.get("data", {})
        
        with self._tracer.start_as_current_span(
            f"{instance.name} publish",
            kind=trace.SpanKind.PRODUCER
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "bullmq")
                span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, instance.name)
                span.set_attribute(SpanAttributes.MESSAGING_OPERATION, "publish")
                span.set_attribute("bullmq.job.name", job_name)
                span.set_attribute("bullmq.queue.name", instance.name)
                
                # Add job data size if available
                if hasattr(job_data, "__len__"):
                    span.set_attribute("bullmq.job.data_size", len(str(job_data)))
                    
            try:
                result = wrapped(*args, **kwargs)
                if span.is_recording() and hasattr(result, "id"):
                    span.set_attribute(SpanAttributes.MESSAGING_MESSAGE_ID, str(result.id))
                return result
            except Exception as exc:
                if span.is_recording():
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    def _trace_queue_add_bulk(self, wrapped, instance, args, kwargs):
        """Trace Queue.add_bulk method"""
        jobs = args[0] if args else kwargs.get("jobs", [])
        job_count = len(jobs) if hasattr(jobs, "__len__") else 0
        
        with self._tracer.start_as_current_span(
            f"{instance.name} publish_bulk",
            kind=trace.SpanKind.PRODUCER
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "bullmq")
                span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, instance.name)
                span.set_attribute(SpanAttributes.MESSAGING_OPERATION, "publish")
                span.set_attribute("bullmq.queue.name", instance.name)
                span.set_attribute("bullmq.jobs.count", job_count)
                span.set_attribute("bullmq.operation", "bulk")
                
            try:
                result = wrapped(*args, **kwargs)
                return result
            except Exception as exc:
                if span.is_recording():
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    def _trace_worker_run(self, wrapped, instance, args, kwargs):
        """Trace Worker.run method"""
        # This method typically runs the worker loop
        # We'll create a span for the worker startup/initialization
        with self._tracer.start_as_current_span(
            f"{instance.name} worker.run",
            kind=trace.SpanKind.CONSUMER
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "bullmq")
                span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, instance.name)
                span.set_attribute(SpanAttributes.MESSAGING_OPERATION, "receive")
                span.set_attribute("bullmq.worker.name", instance.name)
                span.set_attribute("bullmq.worker.concurrency", getattr(instance, "concurrency", 1))
                
            try:
                return wrapped(*args, **kwargs)
            except Exception as exc:
                if span.is_recording():
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise