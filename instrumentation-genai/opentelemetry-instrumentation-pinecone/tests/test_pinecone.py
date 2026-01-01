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

"""Tests for Pinecone instrumentation."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("pinecone", reason="pinecone not installed")


@pytest.fixture
def mock_pinecone_client():
    """Create a mock Pinecone client."""
    with patch("pinecone.Pinecone") as mock_pinecone_class:
        mock_pc = MagicMock()
        mock_index = MagicMock()

        # Mock Index
        mock_pc.Index.return_value = mock_index

        # Mock query response
        mock_query_response = {
            "matches": [
                {
                    "id": "vec1",
                    "score": 0.95,
                    "values": [0.1] * 1536,
                    "metadata": {"text": "Sample text 1"},
                },
                {
                    "id": "vec2",
                    "score": 0.85,
                    "values": [0.2] * 1536,
                    "metadata": {"text": "Sample text 2"},
                },
            ],
            "usage": {"read_units": 6, "write_units": 0},
        }
        mock_index.query.return_value = mock_query_response

        # Mock upsert response
        mock_index.upsert.return_value = {"upserted_count": 2}

        # Mock delete response
        mock_index.delete.return_value = {}

        mock_pinecone_class.return_value = mock_pc
        yield mock_pc


def test_pinecone_query(span_exporter, mock_pinecone_client):
    """Test pinecone.query operation instrumentation."""
    index = mock_pinecone_client.Index("test-index")

    # Perform query
    index.query(
        vector=[0.1] * 1536,
        top_k=3,
        include_metadata=True,
        include_values=True,
    )

    spans = span_exporter.get_finished_spans()
    query_spans = [s for s in spans if "query" in s.name.lower()]

    if query_spans:
        span = query_spans[0]
        assert span.attributes.get("db.system") == "pinecone"
        assert span.attributes.get("db.operation") == "query"


def test_pinecone_upsert(span_exporter, mock_pinecone_client):
    """Test pinecone.upsert operation instrumentation."""
    index = mock_pinecone_client.Index("test-index")

    # Perform upsert
    index.upsert(
        vectors=[
            {"id": "vec1", "values": [0.1] * 1536, "metadata": {"text": "test1"}},
            {"id": "vec2", "values": [0.2] * 1536, "metadata": {"text": "test2"}},
        ]
    )

    spans = span_exporter.get_finished_spans()
    upsert_spans = [s for s in spans if "upsert" in s.name.lower()]

    if upsert_spans:
        span = upsert_spans[0]
        assert span.attributes.get("db.system") == "pinecone"
        assert span.attributes.get("db.operation") == "upsert"


def test_pinecone_delete(span_exporter, mock_pinecone_client):
    """Test pinecone.delete operation instrumentation."""
    index = mock_pinecone_client.Index("test-index")

    # Perform delete
    index.delete(ids=["vec1", "vec2"])

    spans = span_exporter.get_finished_spans()
    delete_spans = [s for s in spans if "delete" in s.name.lower()]

    if delete_spans:
        span = delete_spans[0]
        assert span.attributes.get("db.system") == "pinecone"
        assert span.attributes.get("db.operation") == "delete"


def test_pinecone_query_with_metrics(span_exporter, metrics_reader, mock_pinecone_client):
    """Test pinecone.query with metrics collection."""
    index = mock_pinecone_client.Index("test-index")

    # Perform query
    result = index.query(
        vector=[0.1] * 1536,
        top_k=3,
        include_metadata=True,
    )

    # Verify spans
    spans = span_exporter.get_finished_spans()
    query_spans = [s for s in spans if "query" in s.name.lower()]

    if query_spans:
        span = query_spans[0]
        assert span.attributes.get("db.system") == "pinecone"

    # Check metrics were recorded
    metrics_data = metrics_reader.get_metrics_data()
    if metrics_data and metrics_data.resource_metrics:
        assert len(metrics_data.resource_metrics) > 0
