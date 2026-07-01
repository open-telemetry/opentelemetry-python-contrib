# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from importlib.metadata import PackageNotFoundError
from unittest import TestCase, mock
from unittest.mock import call, patch

import cassandra.cluster
from wrapt import BoundFunctionWrapper

import opentelemetry.instrumentation.cassandra
from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.cassandra import CassandraInstrumentor
from opentelemetry.instrumentation.cassandra.package import (
    _instruments_cassandra_driver,
    _instruments_scylla_driver,
)
from opentelemetry.sdk import resources
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
)
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


class TestCassandraSemconvStability(TestBase):
    def tearDown(self):
        super().tearDown()
        with self.disable_logging():
            CassandraInstrumentor().uninstrument()
        _OpenTelemetrySemanticConventionStability._initialized = False

    @property
    def _mocked_session(self):
        return cassandra.cluster.Session(cluster=mock.Mock(), hosts=[])

    @mock.patch("cassandra.cluster.Cluster.connect")
    @mock.patch("cassandra.cluster.Session.__init__")
    @mock.patch("cassandra.cluster.Session._create_response_future")
    def test_default_semconv(
        self, mock_create_response_future, mock_session_init, mock_connect
    ):
        mock_create_response_future.return_value = mock.Mock()
        mock_session_init.return_value = None
        mock_connect.return_value = self._mocked_session

        CassandraInstrumentor().instrument(include_db_statement=True)
        connect_and_execute_query()

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        span = spans[0]

        self.assertEqual(span.attributes[DB_NAME], "test")
        self.assertEqual(span.attributes[DB_SYSTEM], "cassandra")
        self.assertEqual(span.attributes[DB_STATEMENT], "SELECT * FROM test")
        self.assertIn(NET_PEER_NAME, span.attributes)
        self.assertNotIn(DB_NAMESPACE, span.attributes)
        self.assertNotIn(DB_SYSTEM_NAME, span.attributes)
        self.assertNotIn(DB_QUERY_TEXT, span.attributes)
        self.assertNotIn(SERVER_ADDRESS, span.attributes)

    @mock.patch("cassandra.cluster.Cluster.connect")
    @mock.patch("cassandra.cluster.Session.__init__")
    @mock.patch("cassandra.cluster.Session._create_response_future")
    def test_new_semconv(
        self, mock_create_response_future, mock_session_init, mock_connect
    ):
        mock_create_response_future.return_value = mock.Mock()
        mock_session_init.return_value = None
        mock_connect.return_value = self._mocked_session

        with mock.patch.dict(
            "os.environ",
            {"OTEL_SEMCONV_STABILITY_OPT_IN": "database"},
        ):
            _OpenTelemetrySemanticConventionStability._initialized = False
            CassandraInstrumentor().instrument(include_db_statement=True)
            connect_and_execute_query()

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertEqual(span.attributes[DB_NAMESPACE], "test")
            self.assertEqual(span.attributes[DB_SYSTEM_NAME], "cassandra")
            self.assertEqual(
                span.attributes[DB_QUERY_TEXT], "SELECT * FROM test"
            )
            self.assertIn(SERVER_ADDRESS, span.attributes)
            self.assertNotIn(DB_NAME, span.attributes)
            self.assertNotIn(DB_SYSTEM, span.attributes)
            self.assertNotIn(DB_STATEMENT, span.attributes)
            self.assertNotIn(NET_PEER_NAME, span.attributes)
        _OpenTelemetrySemanticConventionStability._initialized = False

    @mock.patch("cassandra.cluster.Cluster.connect")
    @mock.patch("cassandra.cluster.Session.__init__")
    @mock.patch("cassandra.cluster.Session._create_response_future")
    def test_dup_semconv(
        self, mock_create_response_future, mock_session_init, mock_connect
    ):
        mock_create_response_future.return_value = mock.Mock()
        mock_session_init.return_value = None
        mock_connect.return_value = self._mocked_session

        with mock.patch.dict(
            "os.environ",
            {"OTEL_SEMCONV_STABILITY_OPT_IN": "database/dup"},
        ):
            _OpenTelemetrySemanticConventionStability._initialized = False
            CassandraInstrumentor().instrument(include_db_statement=True)
            connect_and_execute_query()

            spans = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans), 1)
            span = spans[0]

            self.assertEqual(span.attributes[DB_NAME], "test")
            self.assertEqual(span.attributes[DB_SYSTEM], "cassandra")
            self.assertEqual(
                span.attributes[DB_STATEMENT], "SELECT * FROM test"
            )
            self.assertIn(NET_PEER_NAME, span.attributes)
            self.assertEqual(span.attributes[DB_NAMESPACE], "test")
            self.assertEqual(span.attributes[DB_SYSTEM_NAME], "cassandra")
            self.assertEqual(
                span.attributes[DB_QUERY_TEXT], "SELECT * FROM test"
            )
            self.assertIn(SERVER_ADDRESS, span.attributes)
        _OpenTelemetrySemanticConventionStability._initialized = False
