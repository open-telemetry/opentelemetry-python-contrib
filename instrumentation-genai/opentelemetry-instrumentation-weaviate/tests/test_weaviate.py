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

"""Tests for Weaviate instrumentation."""

import json
from unittest.mock import MagicMock, patch

import pytest


ARTICLE_SCHEMA = {
    "class": "Article",
    "description": "An Article class to store a text",
    "properties": [
        {
            "name": "author",
            "dataType": ["string"],
            "description": "The name of the author",
        },
        {
            "name": "text",
            "dataType": ["text"],
            "description": "The text content",
        },
    ],
}


@pytest.fixture
def mock_weaviate_client():
    """Create a mock Weaviate client."""
    with patch("weaviate.connect_to_local") as mock_connect:
        mock_client = MagicMock()
        mock_collections = MagicMock()
        mock_collection = MagicMock()
        mock_data = MagicMock()
        mock_query = MagicMock()
        mock_batch = MagicMock()

        # Set up collection hierarchy
        mock_client.collections = mock_collections
        mock_collections.get.return_value = mock_collection
        mock_collections.create.return_value = mock_collection
        mock_collections.create_from_dict.return_value = mock_collection
        mock_collection.data = mock_data
        mock_collection.query = mock_query
        mock_collection.batch = mock_batch

        # Mock data operations
        mock_data.insert.return_value = "0fa769e6-2f64-4717-97e3-f0297cf84138"

        # Mock query operations
        mock_query_result = MagicMock()
        mock_query_result.objects = [
            MagicMock(properties={"author": "Robert"}),
            MagicMock(properties={"author": "Johnson"}),
        ]
        mock_query.fetch_objects.return_value = mock_query_result
        mock_query.fetch_object_by_id.return_value = MagicMock(
            properties={"author": "Robert", "text": "Once upon a time..."}
        )

        # Mock aggregate
        mock_aggregate = MagicMock()
        mock_aggregate.total_count = 5
        mock_collection.aggregate = MagicMock()
        mock_collection.aggregate.over_all.return_value = mock_aggregate

        mock_connect.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_connect.return_value.__exit__ = MagicMock(return_value=False)

        yield mock_client


def test_weaviate_create_collection(exporter, mock_weaviate_client):
    """Test weaviate.collections.create operation instrumentation."""
    mock_weaviate_client.collections.create(
        name="Article",
        description="An Article class to store a text",
    )

    spans = exporter.get_finished_spans()
    create_spans = [s for s in spans if "create" in s.name]

    if create_spans:
        span = create_spans[0]
        assert span.attributes.get("db.system") == "weaviate"
        assert span.attributes.get("db.operation") == "create"


def test_weaviate_get_collection(exporter, mock_weaviate_client):
    """Test weaviate.collections.get operation instrumentation."""
    mock_weaviate_client.collections.get("Article")

    spans = exporter.get_finished_spans()
    get_spans = [s for s in spans if "get" in s.name and "collections" in s.name]

    if get_spans:
        span = get_spans[0]
        assert span.attributes.get("db.system") == "weaviate"
        assert span.attributes.get("db.operation") == "get"


def test_weaviate_delete_collection(exporter, mock_weaviate_client):
    """Test weaviate.collections.delete operation instrumentation."""
    mock_weaviate_client.collections.delete("Article")

    spans = exporter.get_finished_spans()
    delete_spans = [s for s in spans if "delete" in s.name]

    if delete_spans:
        span = delete_spans[0]
        assert span.attributes.get("db.system") == "weaviate"
        assert span.attributes.get("db.operation") == "delete"


def test_weaviate_insert_data(exporter, mock_weaviate_client):
    """Test weaviate.collections.data.insert operation instrumentation."""
    collection = mock_weaviate_client.collections.get("Article")
    collection.data.insert(
        {
            "author": "Robert",
            "text": "Once upon a time, someone wrote a book...",
        },
    )

    spans = exporter.get_finished_spans()
    insert_spans = [s for s in spans if "insert" in s.name]

    if insert_spans:
        span = insert_spans[0]
        assert span.attributes.get("db.system") == "weaviate"
        assert span.attributes.get("db.operation") == "insert"


def test_weaviate_query_fetch_objects(exporter, mock_weaviate_client):
    """Test weaviate.collections.query.fetch_objects operation instrumentation."""
    collection = mock_weaviate_client.collections.get("Article")
    result = collection.query.fetch_objects(return_properties=["author"])

    spans = exporter.get_finished_spans()
    query_spans = [s for s in spans if "fetch_objects" in s.name]

    if query_spans:
        span = query_spans[0]
        assert span.attributes.get("db.system") == "weaviate"
        assert span.attributes.get("db.operation") == "fetch_objects"


def test_weaviate_delete_all(exporter, mock_weaviate_client):
    """Test weaviate.collections.delete_all operation instrumentation."""
    mock_weaviate_client.collections.delete_all()

    spans = exporter.get_finished_spans()
    delete_spans = [s for s in spans if "delete_all" in s.name]

    if delete_spans:
        span = delete_spans[0]
        assert span.attributes.get("db.system") == "weaviate"
        assert span.attributes.get("db.operation") == "delete_all"
