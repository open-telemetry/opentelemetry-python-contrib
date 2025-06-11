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
    
    # Instrument BullMQ with configuration
    BullMQInstrumentor().instrument(
        emit_create_spans_for_bulk=True,
        require_parent_span_for_publish=False,
        use_producer_span_as_consumer_parent=True
    )
    
    # Create queue and add job
    queue = Queue("myqueue")
    await queue.add("myjob", {"foo": "bar"})
    
    # Create worker to process jobs
    async def process_job(job):
        print(f"Processing job {job.id}: {job.data}")
        return "completed"
    
    worker = Worker("myqueue", process_job)
    await worker.run()

Configuration
-------------

The instrumentation can be configured with the following options:

* ``emit_create_spans_for_bulk``: Whether to create spans for individual jobs in bulk operations (default: False)
* ``require_parent_span_for_publish``: Whether publishing operations require an active parent span (default: False)  
* ``use_producer_span_as_consumer_parent``: Whether consumer spans should use producer spans as parents (default: True)

API
---
"""

import logging
from typing import Collection, Optional
from wrapt import wrap_function_wrapper

from opentelemetry import context as context_api, trace
from opentelemetry.instrumentation.bullmq.package import _instruments
from opentelemetry.instrumentation.bullmq.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.propagate import extract, inject
from opentelemetry.propagators.textmap import Getter, Setter
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace.status import Status, StatusCode

logger = logging.getLogger(__name__)

# BullMQ specific attributes
class BullMQAttributes:
    BULLMQ_JOB_ID = "bullmq.job.id"
    BULLMQ_JOB_NAME = "bullmq.job.name"
    BULLMQ_JOB_DATA_SIZE = "bullmq.job.data_size"
    BULLMQ_JOB_OPTS = "bullmq.job.opts"
    BULLMQ_JOB_DELAY = "bullmq.job.delay"
    BULLMQ_JOB_PRIORITY = "bullmq.job.priority"
    BULLMQ_JOB_ATTEMPTS = "bullmq.job.attempts"
    BULLMQ_JOB_TIMESTAMP = "bullmq.job.timestamp"
    BULLMQ_JOB_PROCESSED_ON = "bullmq.job.processed_on"
    BULLMQ_JOB_FINISHED_ON = "bullmq.job.finished_on"
    BULLMQ_JOB_FAILED_REASON = "bullmq.job.failed_reason"
    BULLMQ_QUEUE_NAME = "bullmq.queue.name"
    BULLMQ_WORKER_NAME = "bullmq.worker.name"
    BULLMQ_WORKER_CONCURRENCY = "bullmq.worker.concurrency"
    BULLMQ_OPERATION = "bullmq.operation"
    BULLMQ_JOBS_COUNT = "bullmq.jobs.count"


class BullMQJobGetter(Getter):
    """Getter for extracting context from BullMQ job options"""
    
    def get(self, carrier, key):
        if hasattr(carrier, 'opts') and isinstance(carrier.opts, dict):
            return carrier.opts.get(key)
        return None
    
    def keys(self, carrier):
        if hasattr(carrier, 'opts') and isinstance(carrier.opts, dict):
            # Only return OpenTelemetry trace header keys
            otel_keys = [k for k in carrier.opts.keys() if k.startswith(('traceparent', 'tracestate', 'baggage'))]
            return otel_keys
        return []


class BullMQJobSetter(Setter):
    """Setter for injecting context into BullMQ job options"""
    
    def set(self, carrier, key, value):
        if hasattr(carrier, 'opts') and isinstance(carrier.opts, dict):
            carrier.opts[key] = value


bullmq_job_getter = BullMQJobGetter()
bullmq_job_setter = BullMQJobSetter()


class BullMQInstrumentor(BaseInstrumentor):
    """An instrumentor for BullMQ"""

    def __init__(self):
        super().__init__()
        self._config = {
            "emit_create_spans_for_bulk": False,
            "require_parent_span_for_publish": False,
            "use_producer_span_as_consumer_parent": True,
        }

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Instruments BullMQ library"""
        tracer_provider = kwargs.get("tracer_provider")
        
        # Update configuration with provided options
        self._config.update({
            k: v for k, v in kwargs.items() 
            if k in self._config and v is not None
        })
        
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
        
        # Instrument Worker operations - we'll hook into job processing
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
        job_opts = args[2] if len(args) > 2 else kwargs.get("opts", {})
        
        # Check if we require a parent span for publishing
        if self._config["require_parent_span_for_publish"]:
            current_span = trace.get_current_span()
            if not current_span or not current_span.is_recording():
                # No active span, skip instrumentation
                return wrapped(*args, **kwargs)
        
        with self._tracer.start_as_current_span(
            f"{instance.name} publish",
            kind=trace.SpanKind.PRODUCER
        ) as span:
            if span.is_recording():
                # Standard messaging attributes
                span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "bullmq")
                span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, instance.name)
                span.set_attribute(SpanAttributes.MESSAGING_OPERATION, "publish")
                
                # BullMQ specific attributes
                span.set_attribute(BullMQAttributes.BULLMQ_JOB_NAME, job_name)
                span.set_attribute(BullMQAttributes.BULLMQ_QUEUE_NAME, instance.name)
                span.set_attribute(BullMQAttributes.BULLMQ_OPERATION, "add")
                
                # Job data size
                if job_data and hasattr(job_data, "__len__"):
                    span.set_attribute(BullMQAttributes.BULLMQ_JOB_DATA_SIZE, len(str(job_data)))
                
                # Job options
                if job_opts:
                    if "delay" in job_opts:
                        span.set_attribute(BullMQAttributes.BULLMQ_JOB_DELAY, job_opts["delay"])
                    if "priority" in job_opts:
                        span.set_attribute(BullMQAttributes.BULLMQ_JOB_PRIORITY, job_opts["priority"])
                    if "attempts" in job_opts:
                        span.set_attribute(BullMQAttributes.BULLMQ_JOB_ATTEMPTS, job_opts["attempts"])
                    
            try:
                # Create a mock job object to inject context into options
                class JobMock:
                    def __init__(self, opts):
                        self.opts = opts if opts else {}
                
                job_mock = JobMock(job_opts)
                
                # Inject trace context into job options for distributed tracing
                inject(job_mock, setter=bullmq_job_setter)
                
                # Update the job options with injected headers
                if len(args) > 2:
                    args = list(args)
                    args[2] = job_mock.opts
                    args = tuple(args)
                else:
                    kwargs["opts"] = job_mock.opts
                
                result = wrapped(*args, **kwargs)
                
                if span.is_recording() and hasattr(result, "id"):
                    span.set_attribute(SpanAttributes.MESSAGING_MESSAGE_ID, str(result.id))
                    span.set_attribute(BullMQAttributes.BULLMQ_JOB_ID, str(result.id))
                    
                    # Add timestamp if available
                    if hasattr(result, "timestamp"):
                        span.set_attribute(BullMQAttributes.BULLMQ_JOB_TIMESTAMP, result.timestamp)
                
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
        
        # Check if we require a parent span for publishing
        if self._config["require_parent_span_for_publish"]:
            current_span = trace.get_current_span()
            if not current_span or not current_span.is_recording():
                return wrapped(*args, **kwargs)
        
        with self._tracer.start_as_current_span(
            f"{instance.name} publish_bulk",
            kind=trace.SpanKind.PRODUCER
        ) as span:
            if span.is_recording():
                # Standard messaging attributes
                span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "bullmq")
                span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, instance.name)
                span.set_attribute(SpanAttributes.MESSAGING_OPERATION, "publish")
                
                # BullMQ specific attributes
                span.set_attribute(BullMQAttributes.BULLMQ_QUEUE_NAME, instance.name)
                span.set_attribute(BullMQAttributes.BULLMQ_JOBS_COUNT, job_count)
                span.set_attribute(BullMQAttributes.BULLMQ_OPERATION, "add_bulk")
                
            try:
                # Process individual jobs if configured
                if self._config["emit_create_spans_for_bulk"] and jobs:
                    processed_jobs = []
                    for job in jobs:
                        job_name = job.get("name", "unknown") if isinstance(job, dict) else "unknown"
                        job_data = job.get("data", {}) if isinstance(job, dict) else {}
                        
                        with self._tracer.start_as_current_span(
                            f"{instance.name} publish",
                            kind=trace.SpanKind.PRODUCER
                        ) as job_span:
                            if job_span.is_recording():
                                job_span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "bullmq")
                                job_span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, instance.name)
                                job_span.set_attribute(SpanAttributes.MESSAGING_OPERATION, "publish")
                                job_span.set_attribute(BullMQAttributes.BULLMQ_JOB_NAME, job_name)
                                job_span.set_attribute(BullMQAttributes.BULLMQ_QUEUE_NAME, instance.name)
                                job_span.set_attribute(BullMQAttributes.BULLMQ_OPERATION, "add")
                                
                                if job_data and hasattr(job_data, "__len__"):
                                    job_span.set_attribute(BullMQAttributes.BULLMQ_JOB_DATA_SIZE, len(str(job_data)))
                            
                            # Inject context into individual job options
                            if isinstance(job, dict):
                                class JobMock:
                                    def __init__(self, opts):
                                        self.opts = opts if opts else {}
                                
                                job_opts = job.get("opts", {})
                                job_mock = JobMock(job_opts)
                                inject(job_mock, setter=bullmq_job_setter)
                                job["opts"] = job_mock.opts
                            
                            processed_jobs.append(job)
                    
                    # Update jobs with trace context
                    if len(args) > 0:
                        args = list(args)
                        args[0] = processed_jobs
                        args = tuple(args)
                    else:
                        kwargs["jobs"] = processed_jobs
                else:
                    # Inject context into job options for bulk operations
                    if jobs:
                        for job in jobs:
                            if isinstance(job, dict):
                                class JobMock:
                                    def __init__(self, opts):
                                        self.opts = opts if opts else {}
                                
                                job_opts = job.get("opts", {})
                                job_mock = JobMock(job_opts)
                                inject(job_mock, setter=bullmq_job_setter)
                                job["opts"] = job_mock.opts
                
                result = wrapped(*args, **kwargs)
                return result
                
            except Exception as exc:
                if span.is_recording():
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    def _trace_worker_run(self, wrapped, instance, args, kwargs):
        """Trace Worker.run method and individual job processing"""
        # We need to instrument job processing, which happens inside the worker
        # For now, we'll hook into the worker initialization and wrap the processor function
        
        # Get the original processor function
        original_processor = getattr(instance, "processor", None)
        
        if original_processor and not hasattr(original_processor, "_bullmq_instrumented"):
            # Wrap the processor function to create spans for individual job processing
            def instrumented_processor(job, *proc_args, **proc_kwargs):
                return self._trace_job_processing(original_processor, job, *proc_args, **proc_kwargs)
            
            # Mark as instrumented to avoid double wrapping
            instrumented_processor._bullmq_instrumented = True
            instance.processor = instrumented_processor
        
        # Create a span for the worker run operation
        with self._tracer.start_as_current_span(
            f"{instance.name} worker.run",
            kind=trace.SpanKind.CONSUMER
        ) as span:
            if span.is_recording():
                span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "bullmq")
                span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, instance.name)
                span.set_attribute(SpanAttributes.MESSAGING_OPERATION, "receive")
                span.set_attribute(BullMQAttributes.BULLMQ_WORKER_NAME, instance.name)
                span.set_attribute(BullMQAttributes.BULLMQ_WORKER_CONCURRENCY, getattr(instance, "concurrency", 1))
                
            try:
                return wrapped(*args, **kwargs)
            except Exception as exc:
                if span.is_recording():
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
    
    def _trace_job_processing(self, processor, job, *args, **kwargs):
        """Create spans for individual job processing"""
        job_name = getattr(job, "name", "unknown")
        job_id = getattr(job, "id", "unknown")
        queue_name = getattr(job, "queue_name", "unknown")
        
        # Extract context from job data for distributed tracing
        parent_context = None
        if self._config["use_producer_span_as_consumer_parent"]:
            parent_context = extract(job, getter=bullmq_job_getter)
        
        with self._tracer.start_as_current_span(
            f"{queue_name} process",
            context=parent_context,
            kind=trace.SpanKind.CONSUMER
        ) as span:
            if span.is_recording():
                # Standard messaging attributes
                span.set_attribute(SpanAttributes.MESSAGING_SYSTEM, "bullmq")
                span.set_attribute(SpanAttributes.MESSAGING_DESTINATION_NAME, queue_name)
                span.set_attribute(SpanAttributes.MESSAGING_OPERATION, "process")
                span.set_attribute(SpanAttributes.MESSAGING_MESSAGE_ID, str(job_id))
                
                # BullMQ specific attributes
                span.set_attribute(BullMQAttributes.BULLMQ_JOB_ID, str(job_id))
                span.set_attribute(BullMQAttributes.BULLMQ_JOB_NAME, job_name)
                span.set_attribute(BullMQAttributes.BULLMQ_QUEUE_NAME, queue_name)
                span.set_attribute(BullMQAttributes.BULLMQ_OPERATION, "process")
                
                # Job timing information
                if hasattr(job, "timestamp"):
                    span.set_attribute(BullMQAttributes.BULLMQ_JOB_TIMESTAMP, job.timestamp)
                if hasattr(job, "processed_on"):
                    span.set_attribute(BullMQAttributes.BULLMQ_JOB_PROCESSED_ON, job.processed_on)
                if hasattr(job, "attempts_made"):
                    span.set_attribute(BullMQAttributes.BULLMQ_JOB_ATTEMPTS, job.attempts_made)
                
                # Job data size
                if hasattr(job, "data") and job.data:
                    span.set_attribute(BullMQAttributes.BULLMQ_JOB_DATA_SIZE, len(str(job.data)))
            
            try:
                result = processor(job, *args, **kwargs)
                
                if span.is_recording():
                    # Add completion timestamp
                    if hasattr(job, "finished_on"):
                        span.set_attribute(BullMQAttributes.BULLMQ_JOB_FINISHED_ON, job.finished_on)
                    
                    # Mark as successful
                    span.set_status(Status(StatusCode.OK))
                
                return result
                
            except Exception as exc:
                if span.is_recording():
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.set_attribute(BullMQAttributes.BULLMQ_JOB_FAILED_REASON, str(exc))
                raise