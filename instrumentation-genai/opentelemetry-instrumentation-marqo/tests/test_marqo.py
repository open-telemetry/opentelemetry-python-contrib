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

"""Tests for Marqo instrumentation."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_marqo_client():
    """Create a mock Marqo client."""
    with patch("marqo.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_index = MagicMock()

        # Mock index operations
        mock_client.create_index.return_value = mock_index
        mock_client.index.return_value = mock_index

        # Mock add_documents response
        mock_index.add_documents.return_value = {
            "items": [
                {"_id": "id1", "status": 200},
                {"_id": "id2", "status": 200},
            ],
            "processingTimeMs": 100.5,
        }

        # Mock search response
        mock_index.search.return_value = {
            "hits": [
                {
                    "_id": "id1",
                    "_score": 0.95,
                    "Title": "The Travels of Marco Polo",
                },
                {
                    "_id": "id2",
                    "_score": 0.85,
                    "Title": "Extravehicular Mobility Unit",
                },
            ],
            "processingTimeMs": 50.2,
        }

        # Mock delete_documents response
        mock_index.delete_documents.return_value = {
            "items": [{"_id": "id1", "status": 200}],
            "status": "succeeded",
        }

        mock_client_class.return_value = mock_client
        yield mock_client


def test_marqo_add_documents(span_exporter, mock_marqo_client):
    """Test marqo.add_documents operation instrumentation."""
    import marqo

    mock_index = mock_marqo_client.index("TestIndex")
    mock_index.add_documents(
        documents=[
            {
                "Title": "The Travels of Marco Polo",
                "Description": "A 13th-century travelogue describing Polo's travels",
            },
            {
                "Title": "Extravehicular Mobility Unit (EMU)",
                "Description": "The EMU is a spacesuit",
            },
        ],
        tensor_fields=["Description"],
    )

    spans = span_exporter.get_finished_spans()
    add_spans = [s for s in spans if "add_documents" in s.name]

    if add_spans:
        span = add_spans[0]
        assert span.attributes.get("db.system") == "marqo"
        assert span.attributes.get("db.operation") == "add_documents"


def test_marqo_search(span_exporter, mock_marqo_client):
    """Test marqo.search operation instrumentation."""
    mock_index = mock_marqo_client.index("TestIndex")
    mock_index.search(
        q="What is the best outfit to wear on the moon?",
    )

    spans = span_exporter.get_finished_spans()
    search_spans = [s for s in spans if "search" in s.name]

    if search_spans:
        span = search_spans[0]
        assert span.attributes.get("db.system") == "marqo"
        assert span.attributes.get("db.operation") == "search"


def test_marqo_delete_documents(span_exporter, mock_marqo_client):
    """Test marqo.delete_documents operation instrumentation."""
    mock_index = mock_marqo_client.index("TestIndex")
    mock_index.delete_documents(ids=["id1"])

    spans = span_exporter.get_finished_spans()
    delete_spans = [s for s in spans if "delete" in s.name]

    if delete_spans:
        span = delete_spans[0]
        assert span.attributes.get("db.system") == "marqo"
        assert span.attributes.get("db.operation") == "delete_documents"
