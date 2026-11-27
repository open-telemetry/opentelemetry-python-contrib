# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

import aiopg
import psycopg2

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.aiopg import AiopgInstrumentor, aiopg_integration
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_OFF,
    Decision,
    Sampler,
    SamplingResult,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.test.samplertestutil import CapturingSampler
from opentelemetry.test.test_base import TestBase

from .test_aiopg_integration import (
    MockCursor,
    async_call,
    mock_connect,
    use_semconv_opt_in,
)


class TestAiopgSampling(TestBase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(aiopg, "connect", mock_connect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        instrumentor = AiopgInstrumentor()
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()
        super().tearDown()

    def test_sampler_sees_query_attributes(self) -> None:
        query = "SELECT * FROM test"
        sampler = CapturingSampler(required_attributes={DB_NAMESPACE: "wanted"})
        tracer_provider, exporter = self.create_tracer_provider(sampler=sampler)
        self.addCleanup(tracer_provider.shutdown)

        with use_semconv_opt_in("database,http"):
            AiopgInstrumentor().instrument(tracer_provider=tracer_provider)
            for database, expected_count in (("other", 0), ("wanted", 1)):
                with self.subTest(database=database):
                    connection = async_call(aiopg.connect(database=database, server_host="db.local", server_port=5432))
                    cursor = async_call(connection.cursor())
                    async_call(cursor.execute(query, rowcount=2))

                    self.assertEqual(cursor.rowcount, 2)
                    spans = exporter.get_finished_spans()
                    self.assertEqual(len(spans), expected_count)
                    self.assertEqual(sampler.name, "SELECT")
                    self.assertEqual(sampler.kind, trace_api.SpanKind.CLIENT)
                    self.assertEqual(
                        sampler.attributes,
                        {
                            DB_SYSTEM_NAME: "postgresql",
                            DB_NAMESPACE: database,
                            DB_QUERY_TEXT: query,
                            SERVER_ADDRESS: "db.local",
                            SERVER_PORT: 5432,
                        },
                    )
                    if spans:
                        self.assertEqual(spans[0].attributes, sampler.attributes)

    def test_sampler_attributes_preserve_query_attributes(self) -> None:
        query = "SELECT * FROM test"
        legacy_attributes = {DB_SYSTEM: "postgresql", DB_NAME: "wanted", DB_STATEMENT: query}
        stable_attributes = {DB_SYSTEM_NAME: "postgresql", DB_NAMESPACE: "wanted", DB_QUERY_TEXT: query}

        for mode, attributes in (
            ("", legacy_attributes),
            ("database", stable_attributes),
            ("database/dup", {**legacy_attributes, **stable_attributes}),
        ):
            attributes = {**attributes, NET_PEER_NAME: "db.local", NET_PEER_PORT: 5432}
            sampler = mock.Mock(spec=Sampler)
            tracer_provider, exporter = self.create_tracer_provider(sampler=sampler)
            self.addCleanup(tracer_provider.shutdown)
            instrumentor = AiopgInstrumentor()
            with use_semconv_opt_in(mode):
                instrumentor.instrument(tracer_provider=tracer_provider)
                try:
                    for collide in (False, True):
                        with self.subTest(mode=mode, collide=collide):
                            sampler_attributes = {"sampler.tag": "kept"}
                            if collide:
                                sampler_attributes.update(
                                    dict.fromkeys(attributes.keys() & {DB_NAME, DB_NAMESPACE, NET_PEER_NAME}, "other")
                                )
                            sampler.should_sample.return_value = SamplingResult(
                                Decision.RECORD_AND_SAMPLE, sampler_attributes
                            )
                            exporter.clear()
                            connection = async_call(
                                aiopg.connect(database="wanted", server_host="db.local", server_port=5432)
                            )
                            cursor = async_call(connection.cursor())
                            async_call(cursor.execute(query))

                            self.assertEqual(sampler.should_sample.call_args.args[4], attributes)
                            spans = exporter.get_finished_spans()
                            self.assertEqual(len(spans), 1)
                            self.assertEqual(spans[0].attributes, {**sampler_attributes, **attributes})
                            self.assertIs(type(spans[0].attributes[NET_PEER_PORT]), int)
                finally:
                    instrumentor.uninstrument()

    def test_dropped_span_attribute_failure_preserves_query_execution(self) -> None:
        class BytesQuery(bytes):
            def decode(self, *args, **kwargs):
                raise RuntimeError("query bytes cannot be decoded by instrumentation")

        query = BytesQuery(b"SELECT * FROM test")
        tracer_provider, exporter = self.create_tracer_provider(sampler=ALWAYS_OFF)
        self.addCleanup(tracer_provider.shutdown)
        AiopgInstrumentor().instrument(tracer_provider=tracer_provider)
        connection = async_call(aiopg.connect(database="test"))
        cursor = async_call(connection.cursor())

        with self.assertLogs("opentelemetry.instrumentation.aiopg.aiopg_integration", level="WARNING"):
            async_call(cursor.execute(query, rowcount=2))
        self.assertEqual(cursor.rowcount, 2)
        self.assertEqual(exporter.get_finished_spans(), ())

        database_error = psycopg2.ProgrammingError("execution failed")
        with (
            mock.patch.object(
                MockCursor, "execute", new_callable=mock.AsyncMock, side_effect=database_error
            ) as execute,
            self.assertLogs("opentelemetry.instrumentation.aiopg.aiopg_integration", level="WARNING"),
            self.assertRaises(psycopg2.ProgrammingError) as caught,
        ):
            async_call(cursor.execute(query))
        execute.assert_awaited_once_with(query)
        self.assertIs(caught.exception, database_error)
        self.assertEqual(exporter.get_finished_spans(), ())

    def test_late_attribute_failure_preserves_completed_groups(self) -> None:
        class FailingParameters(dict):
            def items(self):
                raise ValueError(self["value"])

        query = "SELECT %(value)s"
        parameters = FailingParameters(value="synthetic-sensitive-value")
        sampler = CapturingSampler()
        tracer_provider, exporter = self.create_tracer_provider(sampler=sampler)
        self.addCleanup(tracer_provider.shutdown)

        with use_semconv_opt_in("database,http"):
            integration = aiopg_integration.AiopgIntegration(
                __name__,
                "postgresql",
                {"database": "database", "host": "server_host", "port": "server_port"},
                tracer_provider=tracer_provider,
                capture_parameters=True,
            )
            connection = async_call(
                integration.wrapped_connection(
                    mock_connect,
                    (),
                    {"database": "wanted", "server_host": "db.local", "server_port": 5432},
                )
            )
            cursor = async_call(connection.cursor())
            with (
                mock.patch.object(
                    MockCursor, "execute", new_callable=mock.AsyncMock, return_value=mock.sentinel.query_result
                ) as execute,
                self.assertLogs(aiopg_integration.__name__, level="WARNING") as diagnostics,
            ):
                self.assertIs(async_call(cursor.execute(query, parameters)), mock.sentinel.query_result)
            execute.assert_awaited_once_with(query, parameters)
            self.assertIs(execute.await_args.args[1], parameters)

            with self.subTest("diagnostic"):
                self.assertNotIn(parameters["value"], "\n".join(diagnostics.output))
                self.assertEqual(
                    [record.getMessage() for record in diagnostics.records],
                    ["Failed to collect aiopg span attributes"],
                )
                self.assertIsNone(diagnostics.records[0].exc_info)

            with self.subTest("completed groups"):
                self.assertEqual(
                    sampler.attributes,
                    {
                        DB_SYSTEM_NAME: "postgresql",
                        DB_NAMESPACE: "wanted",
                        DB_QUERY_TEXT: query,
                        SERVER_ADDRESS: "db.local",
                        SERVER_PORT: 5432,
                    },
                )
                spans = exporter.get_finished_spans()
                self.assertEqual(len(spans), 1)
                self.assertEqual(spans[0].attributes, sampler.attributes)

            database_error = psycopg2.ProgrammingError("execution failed")
            with (
                mock.patch.object(
                    MockCursor, "execute", new_callable=mock.AsyncMock, side_effect=database_error
                ) as execute,
                self.assertLogs(aiopg_integration.__name__, level="WARNING"),
                self.assertRaises(psycopg2.ProgrammingError) as caught,
            ):
                async_call(cursor.execute(query, parameters))
            execute.assert_awaited_once_with(query, parameters)
            self.assertIs(execute.await_args.args[1], parameters)
            self.assertIs(caught.exception, database_error)

    def test_suppression_bypasses_attribute_collection(self) -> None:
        sampler = mock.Mock(spec=Sampler)
        tracer_provider, exporter = self.create_tracer_provider(sampler=sampler)
        self.addCleanup(tracer_provider.shutdown)
        AiopgInstrumentor().instrument(tracer_provider=tracer_provider)
        connection = async_call(aiopg.connect(database="test"))
        cursor = async_call(connection.cursor())

        with (
            suppress_instrumentation(),
            mock.patch.object(aiopg_integration.AsyncCursorTracer, "_iter_span_attributes") as collect,
            self.assertNoLogs(aiopg_integration.__name__, level="DEBUG"),
        ):
            async_call(cursor.execute("SELECT 1", rowcount=2))

        collect.assert_not_called()
        sampler.should_sample.assert_not_called()
        self.assertEqual(exporter.get_finished_spans(), ())
        self.assertEqual(cursor.rowcount, 2)
