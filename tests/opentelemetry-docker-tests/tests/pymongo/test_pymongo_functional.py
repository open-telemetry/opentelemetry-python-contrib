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

import os

from pymongo import MongoClient

from opentelemetry import trace as trace_api
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase

MONGODB_HOST = os.getenv("MONGODB_HOST", "localhost")
MONGODB_PORT = int(os.getenv("MONGODB_PORT", "27017"))
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "opentelemetry-tests")
MONGODB_COLLECTION_NAME = "test"


class TestFunctionalPymongo(TestBase):
    def setUp(self):
        super().setUp()
        self._tracer = self.tracer_provider.get_tracer(__name__)
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
        self.assertEqual(
            pymongo_span.attributes[SpanAttributes.DB_NAME], MONGODB_DB_NAME
        )
        self.assertEqual(
            pymongo_span.attributes[SpanAttributes.NET_PEER_NAME], MONGODB_HOST
        )
        self.assertEqual(
            pymongo_span.attributes[SpanAttributes.NET_PEER_PORT], MONGODB_PORT
        )
        self.assertEqual(
            pymongo_span.attributes[SpanAttributes.DB_MONGODB_COLLECTION],
            MONGODB_COLLECTION_NAME,
        )
        self.assertEqual(
            pymongo_span.attributes[SpanAttributes.DB_STATEMENT],
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
