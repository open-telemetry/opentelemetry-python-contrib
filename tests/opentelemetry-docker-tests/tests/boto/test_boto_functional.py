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

import boto3

from opentelemetry.instrumentation.boto import BotoInstrumentor
from opentelemetry.trace import NoOpTracerProvider  # Updated import


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
        spans = (
            self.noop_tracer_provider.get_tracer("test")
            .get_span_processor()
            .spans
        )
        self.assertEqual(len(spans), 0)


if __name__ == "__main__":
    unittest.main()
