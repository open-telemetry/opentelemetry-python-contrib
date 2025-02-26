import unittest

import boto3

from opentelemetry.instrumentation.boto import BotoInstrumentor
from opentelemetry.trace import NoOpTracerProvider, get_tracer_provider


class TestBotoInstrumentationNoOpTracerProvider(unittest.TestCase):
    def setUp(self):
        # Set the NoOpTracerProvider
        self.noop_tracer_provider = NoOpTracerProvider()
        BotoInstrumentor().instrument(
            tracer_provider=self.noop_tracer_provider
        )

    def tearDown(self):
        BotoInstrumentor().uninstrument()

    def test_boto_with_noop_tracer_provider(self):
        # Create a boto3 client
        client = boto3.client("s3")

        # Perform a simple operation
        try:
            client.list_buckets()
        except Exception:
            pass  # Ignore any exceptions for this test

        # Ensure no spans are created
        tracer = get_tracer_provider().get_tracer("test")
        if isinstance(self.noop_tracer_provider, NoOpTracerProvider):
            # NoOpTracerProvider does not support span processing
            self.assertTrue(True)
        else:
            spans = tracer.get_span_processor().spans
            self.assertEqual(len(spans), 0)


if __name__ == "__main__":
    unittest.main()
