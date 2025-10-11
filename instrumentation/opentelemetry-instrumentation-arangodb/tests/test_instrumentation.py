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

from __future__ import annotations

import json
from typing import MutableMapping, Tuple
from unittest.mock import MagicMock

from arango import AQLQueryExecuteError
from arango.api import ApiGroup
from arango.client import ArangoClient
from arango.http import HTTPClient
from arango.response import Response
from requests import Session
from requests_toolbelt import MultipartEncoder
from wrapt import BoundFunctionWrapper

from opentelemetry.instrumentation.arangodb import ArangoDBInstrumentor
from opentelemetry.semconv.attributes import db_attributes, error_attributes
from opentelemetry.test.test_base import TestBase


class MockArangoHTTPClient(HTTPClient):
    def __init__(self):
        super().__init__()
        self.session_mock = MagicMock(Session)
        self.response_mock = MagicMock(Response)

    def clear_mocks(self):
        self.session_mock.reset_mock()
        self.response_mock.reset_mock()

    def create_session(self, host: str) -> Session:
        return self.session_mock

    def send_request(
        self,
        session: Session,
        method: str,
        url: str,
        headers: MutableMapping[str, str] | None = None,
        params: MutableMapping[str, str] | None = None,
        data: str | bytes | MultipartEncoder | None = None,
        auth: Tuple[str, str] | None = None,
    ) -> Response:
        return self.response_mock


class TestArangoDBInstrumentor(TestBase):
    def setUp(self):
        super().setUp()
        ArangoDBInstrumentor().instrument()
        self.assertTrue(isinstance(ApiGroup._execute, BoundFunctionWrapper))

    def tearDown(self):
        ArangoDBInstrumentor().uninstrument()
        self.assertFalse(isinstance(ApiGroup._execute, BoundFunctionWrapper))

    def test_instrumented_span(self):
        mock_http_client = MockArangoHTTPClient()

        client = ArangoClient(
            "http://localhost:8529", http_client=mock_http_client
        )

        mock_http_client.response_mock.status_code = 200
        mock_http_client.response_mock.raw_body = json.dumps(
            {
                "result": [],
                "cached": False,
                "count": 0,
                "extra": {
                    "stats": {"foo": "bar"},
                    "warnings": [{"code": 0, "message": "foo"}],
                },
                "hasMore": False,
            }
        )

        db = client.db("test")
        db.aql.execute("RETURN []", bind_vars={"foo": "bar"}, full_count=True)

        spans = self.memory_exporter.get_finished_spans()
        assert spans
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(
            span.attributes[db_attributes.DB_SYSTEM_NAME], "arangodb"
        )

    def test_instrumented_span_error(self):
        mock_http_client = MockArangoHTTPClient()

        client = ArangoClient(
            "http://localhost:8529", http_client=mock_http_client
        )

        mock_http_client.response_mock.status_code = 400
        mock_http_client.response_mock.raw_body = json.dumps(
            {
                "result": [],
                "hasMore": False,
            }
        )

        db = client.db("test")

        with self.assertRaises(AQLQueryExecuteError):
            db.aql.execute("RETURN []")

        spans = self.memory_exporter.get_finished_spans()
        assert spans
        self.assertEqual(len(spans), 1)
        span = spans[0]
        self.assertEqual(
            span.attributes[error_attributes.ERROR_TYPE],
            "AQLQueryExecuteError",
        )
