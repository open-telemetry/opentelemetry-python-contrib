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

from importlib.metadata import PackageNotFoundError
from unittest import TestCase, mock
from unittest.mock import call, patch

import cassandra.cluster
from wrapt import BoundFunctionWrapper

import opentelemetry.instrumentation.cassandra
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.cassandra import CassandraInstrumentor
from opentelemetry.instrumentation.cassandra.package import (
    _instruments_cassandra_driver,
    _instruments_scylla_driver,
)
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

    @property
    def _mocked_session(self):
        return cassandra.cluster.Session(cluster=mock.Mock(), hosts=[])

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
        mock_connect.return_value = self._mocked_session

        CassandraInstrumentor().instrument()

        connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 1)
        span = spans_list[0]

        # Check version and name in span's instrumentation info
        self.assertEqualSpanInstrumentationScope(
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
        mock_connect.return_value = self._mocked_session

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
        mock_connect.return_value = self._mocked_session

        tracer_provider = trace_api.NoOpTracerProvider()
        CassandraInstrumentor().instrument(tracer_provider=tracer_provider)

        connect_and_execute_query()

        spans_list = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans_list), 0)


class TestCassandraInstrumentationDependencies(TestCase):
    """Tests to verify that the correct package is returned by
    instrumentation_dependencies() depending on which driver is installed.
    This covers the cases where only cassandra-driver is installed,
    only scylla-driver is installed, both are installed, and neither
    is installed.
    """

    @patch("opentelemetry.instrumentation.cassandra.distribution")
    def test_instrumentation_dependencies_cassandra_driver_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = CassandraInstrumentor()

        def _distribution(name):
            if name == "cassandra-driver":
                return None
            raise PackageNotFoundError

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 1)
        self.assertEqual(
            mock_distribution.mock_calls,
            [
                call("cassandra-driver"),
            ],
        )
        self.assertEqual(
            package_to_instrument, (_instruments_cassandra_driver,)
        )

    @patch("opentelemetry.instrumentation.cassandra.distribution")
    def test_instrumentation_dependencies_scylla_driver_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = CassandraInstrumentor()

        def _distribution(name):
            if name == "scylla-driver":
                return None
            raise PackageNotFoundError

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 2)
        self.assertEqual(
            mock_distribution.mock_calls,
            [
                call("cassandra-driver"),
                call("scylla-driver"),
            ],
        )
        self.assertEqual(package_to_instrument, (_instruments_scylla_driver,))

    @patch("opentelemetry.instrumentation.cassandra.distribution")
    def test_instrumentation_dependencies_both_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = CassandraInstrumentor()

        def _distribution(name):
            # The function returns None here for all names
            # to simulate both packages being installed
            return None

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 1)
        self.assertEqual(
            mock_distribution.mock_calls, [call("cassandra-driver")]
        )
        self.assertEqual(
            package_to_instrument, (_instruments_cassandra_driver,)
        )

    @patch("opentelemetry.instrumentation.cassandra.distribution")
    def test_instrumentation_dependencies_none_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = CassandraInstrumentor()

        def _distribution(name):
            # Function raises PackageNotFoundError
            # if name is not in the list. We will
            # raise it for both names to simulate
            # neither being installed
            raise PackageNotFoundError

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 2)
        self.assertEqual(
            mock_distribution.mock_calls,
            [
                call("cassandra-driver"),
                call("scylla-driver"),
            ],
        )
        self.assertEqual(
            package_to_instrument,
            (_instruments_cassandra_driver, _instruments_scylla_driver),
        )
