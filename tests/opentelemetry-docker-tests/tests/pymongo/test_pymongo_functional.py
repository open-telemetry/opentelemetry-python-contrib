# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import contextlib
import os
from unittest import mock

from pymongo import MongoClient

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_MONGODB_COLLECTION,
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
    NET_PEER_PORT,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_COLLECTION_NAME,
    DB_NAMESPACE,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
    SERVER_PORT,
)
from opentelemetry.test.test_base import TestBase

MONGODB_HOST = os.getenv("MONGODB_HOST", "localhost")
MONGODB_PORT = int(os.getenv("MONGODB_PORT", "27017"))
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "opentelemetry-tests")
MONGODB_COLLECTION_NAME = "test"


@contextlib.contextmanager
def use_semconv_opt_in(sem_conv_mode):
    env_patch = mock.patch.dict(
        "os.environ",
        {OTEL_SEMCONV_STABILITY_OPT_IN: sem_conv_mode},
    )
    _OpenTelemetrySemanticConventionStability._initialized = False
    env_patch.start()
    try:
        yield
    finally:
        env_patch.stop()
        _OpenTelemetrySemanticConventionStability._initialized = False


class TestFunctionalPymongo(TestBase):
    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
        PymongoInstrumentor._instance = None
        PymongoInstrumentor._commandtracer_instance = None
        _OpenTelemetrySemanticConventionStability._initialized = False
        self.instrumentor = PymongoInstrumentor()
        self.instrumentor.instrument()
        self.instrumentor._commandtracer_instance._tracer = self._tracer
        self.instrumentor._commandtracer_instance.capture_statement = True
        client = MongoClient(
            MONGODB_HOST, MONGODB_PORT, serverSelectionTimeoutMS=2000
        )
        db = client[MONGODB_DB_NAME]
        self._collection = db[MONGODB_COLLECTION_NAME]

    def tearDown(self):
        self.instrumentor.uninstrument()
        PymongoInstrumentor._instance = None
        PymongoInstrumentor._commandtracer_instance = None
        _OpenTelemetrySemanticConventionStability._initialized = False
        super().tearDown()

    def validate_spans(self, expected_db_statement):
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        for span in spans:
            if span.name == "rootSpan":
                root_span = span
            else:
                pymongo_span = span
            self.assertIsInstance(span.start_time, int)
            self.assertIsInstance(span.end_time, int)
        self.assertIsNot(root_span, None)
        self.assertIsNot(pymongo_span, None)
        self.assertIsNotNone(pymongo_span.parent)
        self.assertIs(pymongo_span.parent, root_span.get_span_context())
        self.assertIs(pymongo_span.kind, trace_api.SpanKind.CLIENT)
        self.assertEqual(pymongo_span.attributes[DB_NAME], MONGODB_DB_NAME)
        self.assertEqual(pymongo_span.attributes[NET_PEER_NAME], MONGODB_HOST)
        self.assertEqual(pymongo_span.attributes[NET_PEER_PORT], MONGODB_PORT)
        self.assertEqual(
            pymongo_span.attributes[DB_MONGODB_COLLECTION],
            MONGODB_COLLECTION_NAME,
        )
        self.assertEqual(
            pymongo_span.attributes[DB_STATEMENT],
            expected_db_statement,
        )

    def test_insert(self):
        """Should create a child span for insert"""
        with self._tracer.start_as_current_span("rootSpan"):
            insert_result = self._collection.insert_one(
                {"name": "testName", "value": "testValue"}
            )
            insert_result_id = insert_result.inserted_id

        expected_db_statement = (
            f"insert [{{'name': 'testName', 'value': 'testValue', '_id': "
            f"ObjectId('{insert_result_id}')}}]"
        )
        self.validate_spans(expected_db_statement)

    def test_update(self):
        """Should create a child span for update"""
        with self._tracer.start_as_current_span("rootSpan"):
            self._collection.update_one(
                {"name": "testName"}, {"$set": {"value": "someOtherValue"}}
            )

        expected_db_statement = (
            "update [SON([('q', {'name': 'testName'}), ('u', "
            "{'$set': {'value': 'someOtherValue'}}), ('multi', False), ('upsert', False)])]"
        )
        self.validate_spans(expected_db_statement)

    def test_find(self):
        """Should create a child span for find"""
        with self._tracer.start_as_current_span("rootSpan"):
            self._collection.find_one({"name": "testName"})

        expected_db_statement = "find {'name': 'testName'}"
        self.validate_spans(expected_db_statement)

    def test_delete(self):
        """Should create a child span for delete"""
        with self._tracer.start_as_current_span("rootSpan"):
            self._collection.delete_one({"name": "testName"})

        expected_db_statement = (
            "delete [SON([('q', {'name': 'testName'}), ('limit', 1)])]"
        )
        self.validate_spans(expected_db_statement)

    def test_find_without_capture_statement(self):
        """Should create a child span for find"""
        self.instrumentor._commandtracer_instance.capture_statement = False

        with self._tracer.start_as_current_span("rootSpan"):
            self._collection.find_one({"name": "testName"})

        expected_db_statement = "find"
        self.validate_spans(expected_db_statement)

    def test_uninstrument(self):
        # check that integration is working
        self._collection.find_one()
        spans = self.memory_exporter.get_finished_spans()
        self.memory_exporter.clear()
        self.assertEqual(len(spans), 1)

        # uninstrument and check not new spans are created
        PymongoInstrumentor().uninstrument()
        self._collection.find_one()
        spans = self.memory_exporter.get_finished_spans()
        self.memory_exporter.clear()
        self.assertEqual(len(spans), 0)

        # re-enable and check that it works again
        PymongoInstrumentor().instrument()
        self._collection.find_one()
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)

    def test_find_stable_semconv(self):
        with use_semconv_opt_in("database"):
            self.instrumentor.uninstrument()
            self.instrumentor._commandtracer_instance = None
            self.instrumentor.instrument()
            self.instrumentor._commandtracer_instance._tracer = self._tracer
            self.instrumentor._commandtracer_instance.capture_statement = True
            with self._tracer.start_as_current_span("rootSpan"):
                self._collection.find_one({"name": "testName"})

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        pymongo_span = next(s for s in spans if s.name != "rootSpan")
        self.assertEqual(pymongo_span.attributes[DB_SYSTEM_NAME], "mongodb")
        self.assertEqual(
            pymongo_span.attributes[DB_NAMESPACE], MONGODB_DB_NAME
        )
        self.assertEqual(
            pymongo_span.attributes[DB_QUERY_TEXT],
            "find {'name': 'testName'}",
        )
        self.assertEqual(pymongo_span.attributes[SERVER_ADDRESS], MONGODB_HOST)
        self.assertEqual(pymongo_span.attributes[SERVER_PORT], MONGODB_PORT)
        self.assertEqual(
            pymongo_span.attributes[DB_COLLECTION_NAME],
            MONGODB_COLLECTION_NAME,
        )
        self.assertNotIn(DB_SYSTEM, pymongo_span.attributes)
        self.assertNotIn(DB_NAME, pymongo_span.attributes)
        self.assertNotIn(DB_STATEMENT, pymongo_span.attributes)
        self.assertNotIn(NET_PEER_NAME, pymongo_span.attributes)
        self.assertNotIn(NET_PEER_PORT, pymongo_span.attributes)
        self.assertNotIn(DB_MONGODB_COLLECTION, pymongo_span.attributes)
