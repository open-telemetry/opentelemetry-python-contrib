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

"""Tests for LanceDB instrumentation."""

import tempfile

import lancedb
import pytest
from opentelemetry.instrumentation.lancedb.semconv import LanceDBAttributes
from opentelemetry.trace import SpanKind


@pytest.fixture
def lance_db():
    """Create a temporary LanceDB connection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = lancedb.connect(tmpdir)
        yield db


@pytest.fixture
def table(lance_db):
    """Create a test table."""
    data = [
        {"vector": [1.3, 1.4], "item": "fizz", "price": 100.0},
        {"vector": [9.5, 56.2], "item": "buzz", "price": 200.0},
    ]
    tbl = lance_db.create_table("my_table", data=data)
    yield tbl
    lance_db.drop_table("my_table")


def test_lancedb_add(exporter, lance_db, table):
    """Test lancedb.add operation instrumentation."""
    exporter.clear()
    data_to_add = [
        {"vector": [1.3, 1.4], "item": "fizz2", "price": 150.0},
        {"vector": [9.5, 56.2], "item": "buzz2", "price": 250.0},
    ]
    table.add(data=data_to_add)

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "lancedb.add")

    assert span.kind == SpanKind.CLIENT
    assert span.attributes.get("db.system") == "lancedb"
    assert span.attributes.get("db.operation") == "add"
    assert span.attributes.get(LanceDBAttributes.ADD_DATA_COUNT) == 2


def test_lancedb_search(exporter, lance_db, table):
    """Test lancedb.search operation instrumentation."""
    table.search(query=[100, 100]).limit(2).to_list()

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "lancedb.search")

    assert span.kind == SpanKind.CLIENT
    assert span.attributes.get("db.system") == "lancedb"
    assert span.attributes.get("db.operation") == "search"
    assert span.attributes.get(LanceDBAttributes.SEARCH_QUERY) == "[100, 100]"


def test_lancedb_delete(exporter, lance_db, table):
    """Test lancedb.delete operation instrumentation."""
    table.delete(where='item = "fizz"')

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "lancedb.delete")

    assert span.kind == SpanKind.CLIENT
    assert span.attributes.get("db.system") == "lancedb"
    assert span.attributes.get("db.operation") == "delete"
    assert span.attributes.get(LanceDBAttributes.DELETE_WHERE) == 'item = "fizz"'
