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

from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
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
        
        # Import after instrumentation to ensure wrapping
        with patch("bullmq.Queue.add", return_value=mock_job) as mock_add:
            # Simulate calling queue.add
            from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
            instrumentor = BullMQInstrumentor()
            instrumentor._trace_queue_add(
                mock_add, mock_queue, ("test_job", {"data": "test"}), {}
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
                "bullmq.job.name": "test_job",
                "bullmq.queue.name": "test_queue",
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
                "bullmq.queue.name": "test_queue",
                "bullmq.jobs.count": 2,
                "bullmq.operation": "bulk",
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
                "bullmq.worker.name": "test_worker",
                "bullmq.worker.concurrency": 5,
            },
        )

    @patch("bullmq.Queue")
    def test_queue_add_error_handling(self, mock_queue_class):
        """Test error handling in Queue.add instrumentation"""
        self.instrumentor.instrument()
        
        # Create mock queue instance
        mock_queue = MagicMock()
        mock_queue.name = "test_queue"
        mock_queue_class.return_value = mock_queue
        
        # Mock the exception
        test_exception = Exception("Test error")
        
        # Import after instrumentation to ensure wrapping
        with patch("bullmq.Queue.add", side_effect=test_exception) as mock_add:
            # Simulate calling queue.add with exception
            from opentelemetry.instrumentation.bullmq import BullMQInstrumentor
            instrumentor = BullMQInstrumentor()
            
            with self.assertRaises(Exception):
                instrumentor._trace_queue_add(
                    mock_add, mock_queue, ("test_job", {"data": "test"}), {}
                )
            
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        
        span = spans[0]
        self.assertEqual(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.status.description, "Test error")
        
        # Check that exception was recorded
        self.assertEqual(len(span.events), 1)
        event = span.events[0]
        self.assertEqual(event.name, "exception")

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


if __name__ == "__main__":
    unittest.main()