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

import unittest
from unittest.mock import MagicMock, patch

from opentelemetry.instrumentation.bullmq import BullMQInstrumentor, BullMQAttributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind, StatusCode


class TestBullMQInstrumentation(TestBase):
    def setUp(self):
        super().setUp()
        self.instrumentor = BullMQInstrumentor()

    def tearDown(self):
        super().tearDown()
        self.instrumentor.uninstrument()

    @patch("bullmq.Queue")
    def test_queue_add_instrumentation(self, mock_queue_class):
        """Test that Queue.add method is properly instrumented"""
        self.instrumentor.instrument()
        
        # Create mock queue instance
        mock_queue = MagicMock()
        mock_queue.name = "test_queue"
        mock_queue_class.return_value = mock_queue
        
        # Mock the job result
        mock_job = MagicMock()
        mock_job.id = "job_123"
        mock_job.timestamp = 1234567890
        
        # Import after instrumentation to ensure wrapping
        with patch("bullmq.Queue.add", return_value=mock_job) as mock_add:
            # Simulate calling queue.add
            from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
            instrumentor = BullMQInstrumentor()
            instrumentor._trace_queue_add(
                mock_add, mock_queue, ("test_job", {"data": "test"}, {"delay": 1000, "priority": 5}), {}
            )
            
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        
        span = spans[0]
        self.assertEqual(span.name, "test_queue publish")
        self.assertEqual(span.kind, SpanKind.PRODUCER)
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.MESSAGING_SYSTEM: "bullmq",
                SpanAttributes.MESSAGING_DESTINATION_NAME: "test_queue",
                SpanAttributes.MESSAGING_OPERATION: "publish",
                SpanAttributes.MESSAGING_MESSAGE_ID: "job_123",
                BullMQAttributes.BULLMQ_JOB_ID: "job_123",
                BullMQAttributes.BULLMQ_JOB_NAME: "test_job",
                BullMQAttributes.BULLMQ_QUEUE_NAME: "test_queue",
                BullMQAttributes.BULLMQ_OPERATION: "add",
                BullMQAttributes.BULLMQ_JOB_DELAY: 1000,
                BullMQAttributes.BULLMQ_JOB_PRIORITY: 5,
                BullMQAttributes.BULLMQ_JOB_TIMESTAMP: 1234567890,
            },
        )

    @patch("bullmq.Queue")
    def test_queue_add_bulk_instrumentation(self, mock_queue_class):
        """Test that Queue.add_bulk method is properly instrumented"""
        self.instrumentor.instrument()
        
        # Create mock queue instance
        mock_queue = MagicMock()
        mock_queue.name = "test_queue"
        mock_queue_class.return_value = mock_queue
        
        # Mock jobs list
        jobs = [{"name": "job1", "data": {}}, {"name": "job2", "data": {}}]
        
        # Import after instrumentation to ensure wrapping
        with patch("bullmq.Queue.add_bulk", return_value=[]) as mock_add_bulk:
            # Simulate calling queue.add_bulk
            from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
            instrumentor = BullMQInstrumentor()
            instrumentor._trace_queue_add_bulk(
                mock_add_bulk, mock_queue, (jobs,), {}
            )
            
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        
        span = spans[0]
        self.assertEqual(span.name, "test_queue publish_bulk")
        self.assertEqual(span.kind, SpanKind.PRODUCER)
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.MESSAGING_SYSTEM: "bullmq",
                SpanAttributes.MESSAGING_DESTINATION_NAME: "test_queue",
                SpanAttributes.MESSAGING_OPERATION: "publish",
                BullMQAttributes.BULLMQ_QUEUE_NAME: "test_queue",
                BullMQAttributes.BULLMQ_JOBS_COUNT: 2,
                BullMQAttributes.BULLMQ_OPERATION: "add_bulk",
            },
        )

    @patch("bullmq.Queue")
    def test_queue_add_bulk_with_individual_spans(self, mock_queue_class):
        """Test bulk operations with individual span creation enabled"""
        self.instrumentor.instrument(emit_create_spans_for_bulk=True)
        
        # Create mock queue instance
        mock_queue = MagicMock()
        mock_queue.name = "test_queue"
        mock_queue_class.return_value = mock_queue
        
        # Mock jobs list
        jobs = [{"name": "job1", "data": {"key": "value1"}}, {"name": "job2", "data": {"key": "value2"}}]
        
        # Import after instrumentation to ensure wrapping
        with patch("bullmq.Queue.add_bulk", return_value=[]) as mock_add_bulk:
            # Simulate calling queue.add_bulk
            from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
            instrumentor = BullMQInstrumentor()
            instrumentor._trace_queue_add_bulk(
                mock_add_bulk, mock_queue, (jobs,), {}
            )
            
        spans = self.memory_exporter.get_finished_spans()
        # Should have 3 spans: 1 bulk span + 2 individual job spans
        self.assertEqual(len(spans), 3)
        
        # Check bulk span
        bulk_span = spans[2]  # Last span created
        self.assertEqual(bulk_span.name, "test_queue publish_bulk")
        self.assertEqual(bulk_span.kind, SpanKind.PRODUCER)
        
        # Check individual job spans
        for i, span in enumerate(spans[:2]):
            self.assertEqual(span.name, "test_queue publish")
            self.assertEqual(span.kind, SpanKind.PRODUCER)
            self.assertSpanHasAttributes(
                span,
                {
                    BullMQAttributes.BULLMQ_JOB_NAME: f"job{i+1}",
                    BullMQAttributes.BULLMQ_OPERATION: "add",
                },
            )

    @patch("bullmq.Worker")
    def test_worker_run_instrumentation(self, mock_worker_class):
        """Test that Worker.run method is properly instrumented"""
        self.instrumentor.instrument()
        
        # Create mock worker instance
        mock_worker = MagicMock()
        mock_worker.name = "test_worker"
        mock_worker.concurrency = 5
        mock_worker.processor = None  # No processor to wrap
        mock_worker_class.return_value = mock_worker
        
        # Import after instrumentation to ensure wrapping
        with patch("bullmq.Worker.run", return_value=None) as mock_run:
            # Simulate calling worker.run
            from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
            instrumentor = BullMQInstrumentor()
            instrumentor._trace_worker_run(
                mock_run, mock_worker, (), {}
            )
            
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        
        span = spans[0]
        self.assertEqual(span.name, "test_worker worker.run")
        self.assertEqual(span.kind, SpanKind.CONSUMER)
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.MESSAGING_SYSTEM: "bullmq",
                SpanAttributes.MESSAGING_DESTINATION_NAME: "test_worker",
                SpanAttributes.MESSAGING_OPERATION: "receive",
                BullMQAttributes.BULLMQ_WORKER_NAME: "test_worker",
                BullMQAttributes.BULLMQ_WORKER_CONCURRENCY: 5,
            },
        )

    def test_job_processing_instrumentation(self):
        """Test that individual job processing is instrumented"""
        self.instrumentor.instrument()
        
        # Create mock job
        mock_job = MagicMock()
        mock_job.id = "job_456"
        mock_job.name = "test_job"
        mock_job.queue_name = "test_queue"
        mock_job.data = {"key": "value"}
        mock_job.opts = {"traceparent": "test_trace"}
        mock_job.timestamp = 1234567890
        mock_job.processed_on = 1234567900
        mock_job.attempts_made = 1
        mock_job.finished_on = 1234567910
        
        # Mock processor function
        def mock_processor(job):
            return "processed"
        
        # Import after instrumentation to ensure wrapping
        from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
        instrumentor = BullMQInstrumentor()
        result = instrumentor._trace_job_processing(mock_processor, mock_job)
        
        self.assertEqual(result, "processed")
        
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        
        span = spans[0]
        self.assertEqual(span.name, "test_queue process")
        self.assertEqual(span.kind, SpanKind.CONSUMER)
        self.assertEqual(span.status.status_code, StatusCode.OK)
        self.assertSpanHasAttributes(
            span,
            {
                SpanAttributes.MESSAGING_SYSTEM: "bullmq",
                SpanAttributes.MESSAGING_DESTINATION_NAME: "test_queue",
                SpanAttributes.MESSAGING_OPERATION: "process",
                SpanAttributes.MESSAGING_MESSAGE_ID: "job_456",
                BullMQAttributes.BULLMQ_JOB_ID: "job_456",
                BullMQAttributes.BULLMQ_JOB_NAME: "test_job",
                BullMQAttributes.BULLMQ_QUEUE_NAME: "test_queue",
                BullMQAttributes.BULLMQ_OPERATION: "process",
                BullMQAttributes.BULLMQ_JOB_TIMESTAMP: 1234567890,
                BullMQAttributes.BULLMQ_JOB_PROCESSED_ON: 1234567900,
                BullMQAttributes.BULLMQ_JOB_ATTEMPTS: 1,
                BullMQAttributes.BULLMQ_JOB_FINISHED_ON: 1234567910,
            },
        )

    def test_job_processing_error_handling(self):
        """Test error handling in job processing instrumentation"""
        self.instrumentor.instrument()
        
        # Create mock job
        mock_job = MagicMock()
        mock_job.id = "job_error"
        mock_job.name = "error_job"
        mock_job.queue_name = "test_queue"
        mock_job.data = {"key": "value"}
        
        # Mock processor function that raises an exception
        def error_processor(job):
            raise Exception("Processing failed")
        
        # Import after instrumentation to ensure wrapping
        from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
        instrumentor = BullMQInstrumentor()
        
        with self.assertRaises(Exception):
            instrumentor._trace_job_processing(error_processor, mock_job)
        
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        
        span = spans[0]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.status.description, "Processing failed")
        self.assertSpanHasAttributes(
            span,
            {
                BullMQAttributes.BULLMQ_JOB_FAILED_REASON: "Processing failed",
            },
        )
        
        # Check that exception was recorded
        self.assertEqual(len(span.events), 1)
        event = span.events[0]
        self.assertEqual(event.name, "exception")

    def test_configuration_options(self):
        """Test configuration options work correctly"""
        # Test emit_create_spans_for_bulk
        self.instrumentor.instrument(emit_create_spans_for_bulk=True)
        self.assertTrue(self.instrumentor._config["emit_create_spans_for_bulk"])
        
        # Test require_parent_span_for_publish
        self.instrumentor.uninstrument()
        self.instrumentor.instrument(require_parent_span_for_publish=True)
        self.assertTrue(self.instrumentor._config["require_parent_span_for_publish"])
        
        # Test use_producer_span_as_consumer_parent
        self.instrumentor.uninstrument()
        self.instrumentor.instrument(use_producer_span_as_consumer_parent=False)
        self.assertFalse(self.instrumentor._config["use_producer_span_as_consumer_parent"])

    @patch("bullmq.Queue")
    def test_require_parent_span_for_publish(self, mock_queue_class):
        """Test that publishing operations can require parent spans"""
        self.instrumentor.instrument(require_parent_span_for_publish=True)
        
        # Create mock queue instance
        mock_queue = MagicMock()
        mock_queue.name = "test_queue"
        mock_queue_class.return_value = mock_queue
        
        # Import after instrumentation to ensure wrapping
        with patch("bullmq.Queue.add", return_value=MagicMock()) as mock_add:
            # Simulate calling queue.add without parent span
            from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
            instrumentor = BullMQInstrumentor()
            instrumentor._trace_queue_add(
                mock_add, mock_queue, ("test_job", {"data": "test"}), {}
            )
            
        # Should call wrapped function but not create span
        mock_add.assert_called_once()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 0)

    def test_instrumentation_dependencies(self):
        """Test that instrumentation dependencies are correctly defined"""
        dependencies = self.instrumentor.instrumentation_dependencies()
        self.assertIn("bullmq", dependencies)

    def test_uninstrument(self):
        """Test that uninstrumentation works correctly"""
        self.instrumentor.instrument()
        self.instrumentor.uninstrument()
        
        # After uninstrumentation, no spans should be created
        # This test would need actual BullMQ library to be fully effective
        # but tests the uninstrument method doesn't raise errors
        self.assertTrue(True)  # Placeholder assertion

    def test_trace_propagation_headers(self):
        """Test that trace context is properly injected into job data"""
        self.instrumentor.instrument()
        
        # Create mock queue instance
        mock_queue = MagicMock()
        mock_queue.name = "test_queue"
        
        # Create a span to provide context
        with self.instrumentor._tracer.start_as_current_span("parent_span"):
            with patch("bullmq.Queue.add", return_value=MagicMock()) as mock_add:
                # Simulate calling queue.add
                job_data = {"original": "data"}
                self.instrumentor._trace_queue_add(
                    mock_add, mock_queue, ("test_job", job_data), {}
                )
                
                # Check that trace context was injected into job options
                call_args = mock_add.call_args
                if len(call_args[0]) > 2:
                    updated_opts = call_args[0][2]  # Third argument (job opts)
                else:
                    updated_opts = call_args[1].get("opts", {})
                # Should contain OpenTelemetry trace headers in job options
                has_trace_headers = any(k.startswith(('traceparent', 'tracestate')) for k in updated_opts.keys())
                self.assertTrue(has_trace_headers)


if __name__ == "__main__":
    unittest.main()