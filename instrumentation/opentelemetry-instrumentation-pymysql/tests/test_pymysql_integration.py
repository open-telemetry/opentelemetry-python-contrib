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

from unittest.mock import Mock, patch

import pymysql

import opentelemetry.instrumentation.pymysql
from opentelemetry.instrumentation.pymysql import PyMySQLInstrumentor
from opentelemetry.sdk import resources
from opentelemetry.test.test_base import TestBase
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.metrics import MetricInstruments
from opentelemetry.sdk.metrics.export import HistogramDataPoint

def mock_connect(*args, **kwargs):
    class MockConnection:
        def cursor(self):
            # pylint: disable=no-self-use
            return Mock()

    return MockConnection()


class TestPyMysqlIntegration(TestBase):
    def setUp(self):
        self.meter = get_meter(__name__)
        
    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            PyMySQLInstrumentor().uninstrument()

    @patch("pymysql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_instrumentor(self):
        PyMySQLInstrumentor().instrument()

        cnx = pymysql.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.pymysql
        )

        # check that no spans are generated after uninstrument
        PyMySQLInstrumentor().uninstrument()

        cnx = pymysql.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @patch("pymysql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_custom_tracer_provider(self):
        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        PyMySQLInstrumentor().instrument(tracer_provider=tracer_provider)

        cnx = pymysql.connect(database="test")
        cursor = cnx.cursor()
        query = "SELECT * FROM test"
        cursor.execute(query)

        spans_list = exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        self.assertIs(span.resource, resource)

    @patch("pymysql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_instrument_connection(self):
        cnx = pymysql.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)

        cnx = PyMySQLInstrumentor().instrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @patch("pymysql.connect", new=mock_connect)
    # pylint: disable=unused-argument
    def test_uninstrument_connection(self):
        PyMySQLInstrumentor().instrument()
        cnx = pymysql.connect(database="test")
        query = "SELECT * FROM test"
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

        cnx = PyMySQLInstrumentor().uninstrument_connection(cnx)
        cursor = cnx.cursor()
        cursor.execute(query)

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    def test_createtime_histogram(self):
        createtime_histogram = self.meter.create_histogram(
            name=MetricInstruments.db.client.connections.create_time,
            description="The time it took to create a new connection",
            unit="ms",
        )
        
        data = createtime_histogram.checkpoint().popitem()[1]
        self.assertIsInstance(data, HistogramDataPoint)
        self.assertIsNotNone(data.value.sum)
        self.assertIsNotNone(data.value.count)
        
    def test_pending_requests_updowncounter(self):
        pending_requests_updowncounter = self.meter.create_up_down_counter(
            name=MetricInstruments.db.client.connections.pending_requests,
            description="The number of pending requests for an open connection, cumulative for the entire pool.",
            unit="requests",
        )
        data = pending_requests_updowncounter.checkpoint().popitem()[1]
        self.assertIsNotNone(data.value)

    def test_connectionusage_updowncounter(self):
        connectionusage_updowncounter = self.meter.create_up_down_counter(
            name=MetricInstruments.db.client.connections.usage,
            description="The number of connections that are currently in state described by the state attribute",
            unit="connections",
        )
        self.assertIsNotNone(connectionusage_updowncounter)
        self.connectionusage_updowncounter.add()
        self.assertEqual(self.connectionusage_updowncounter.count, 1)

        self.connectionusage_updowncounter.add()
        self.assertEqual(self.connectionusage_updowncounter.count, 2)

        self.connectionusage_updowncounter.subtract()
        self.assertEqual(self.connectionusage_updowncounter.count, 1)


