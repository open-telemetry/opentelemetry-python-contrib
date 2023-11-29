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

from unittest import mock

import cassandra.cluster
from wrapt import BoundFunctionWrapper

import opentelemetry.instrumentation.cassandra
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.cassandra import CassandraInstrumentor
from opentelemetry.sdk import resources
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind


def connect_and_execute_query():
    cluster = cassandra.cluster.Cluster()
    cluster._is_setup = True
    session = cluster.connect()
    session.cluster = cluster
    session.keyspace = "test"
    session._request_init_callbacks = []
    query = "SELECT * FROM test"
    session.execute(query)
    return cluster, session, query


class TestCassandraIntegration(TestBase):
    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            CassandraInstrumentor().uninstrument()

    def test_instrument_uninstrument(self):
        instrumentation = CassandraInstrumentor()
        instrumentation.instrument()
        self.assertTrue(
            isinstance(
                cassandra.cluster.Session.execute_async, BoundFunctionWrapper
            )
        )

        instrumentation.uninstrument()
        self.assertFalse(
            isinstance(
                cassandra.cluster.Session.execute_async, BoundFunctionWrapper
            )
        )

    @mock.patch("cassandra.cluster.Cluster.connect")
    @mock.patch("cassandra.cluster.Session.__init__")
    @mock.patch("cassandra.cluster.Session._create_response_future")
    def test_instrumentor(
        self, mock_create_response_future, mock_session_init, mock_connect
    ):
        mock_create_response_future.return_value = mock.Mock()
        mock_session_init.return_value = None
        mock_connect.return_value = cassandra.cluster.Session()

        CassandraInstrumentor().instrument()

        connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationInfo(
            span, opentelemetry.instrumentation.cassandra
        )
        self.assertEqual(span.name, "Cassandra")
        self.assertEqual(span.kind, SpanKind.CLIENT)

        # check that no spans are generated after uninstrument
        CassandraInstrumentor().uninstrument()

        connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)

    @mock.patch("cassandra.cluster.Cluster.connect")
    @mock.patch("cassandra.cluster.Session.__init__")
    @mock.patch("cassandra.cluster.Session._create_response_future")
    def test_custom_tracer_provider(
        self, mock_create_response_future, mock_session_init, mock_connect
    ):
        mock_create_response_future.return_value = mock.Mock()
        mock_session_init.return_value = None
        mock_connect.return_value = cassandra.cluster.Session()

        resource = resources.Resource.create({})
        result = self.create_tracer_provider(resource=resource)
        tracer_provider, exporter = result

        CassandraInstrumentor().instrument(tracer_provider=tracer_provider)

        connect_and_execute_query()

        span_list = exporter.get_finished_spans()
        self.assertEqual(len(span_list), 1)
        span = span_list[0]

        self.assertIs(span.resource, resource)

    @mock.patch("cassandra.cluster.Cluster.connect")
    @mock.patch("cassandra.cluster.Session.__init__")
    @mock.patch("cassandra.cluster.Session._create_response_future")
    def test_instrument_connection_no_op_tracer_provider(
        self, mock_create_response_future, mock_session_init, mock_connect
    ):
        mock_create_response_future.return_value = mock.Mock()
        mock_session_init.return_value = None
        mock_connect.return_value = cassandra.cluster.Session()

        tracer_provider = trace_api.NoOpTracerProvider()
        CassandraInstrumentor().instrument(tracer_provider=tracer_provider)

        connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)
