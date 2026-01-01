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

"""Tests for Qdrant instrumentation."""

import pytest
from opentelemetry.instrumentation.qdrant.semconv import QdrantAttributes
from opentelemetry.trace import SpanKind
from qdrant_client import QdrantClient, models

COLLECTION_NAME = "test_collection"
EMBEDDING_DIM = 384


@pytest.fixture
def qdrant():
    """Return an empty in-memory QdrantClient instance for each test."""
    yield QdrantClient(location=":memory:")


def upsert(qdrant: QdrantClient):
    """Create collection and upsert points."""
    qdrant.create_collection(
        COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=EMBEDDING_DIM, distance=models.Distance.COSINE
        ),
    )

    qdrant.upsert(
        COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=1, vector=[0.1] * EMBEDDING_DIM, payload={"name": "Paul"}
            ),
            models.PointStruct(
                id=2, vector=[0.2] * EMBEDDING_DIM, payload={"name": "John"}
            ),
        ],
    )


def test_qdrant_upsert(span_exporter, qdrant):
    """Test qdrant.upsert operation."""
    upsert(qdrant)

    spans = span_exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "qdrant.upsert")

    assert span.kind == SpanKind.CLIENT
    assert span.attributes.get(QdrantAttributes.COLLECTION_NAME) == COLLECTION_NAME
    assert span.attributes.get(QdrantAttributes.UPSERT_POINTS_COUNT) == 2


def upload_collection(qdrant: QdrantClient):
    """Create collection and upload vectors."""
    qdrant.create_collection(
        COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=EMBEDDING_DIM, distance=models.Distance.COSINE
        ),
    )

    qdrant.upload_collection(
        COLLECTION_NAME,
        vectors=[
            [0.1] * EMBEDDING_DIM,
            [0.2] * EMBEDDING_DIM,
            [0.3] * EMBEDDING_DIM,
        ],
        ids=[3, 21, 1],
        payload=[{"name": "Paul"}, {"name": "John"}, {}],
    )


def test_qdrant_upload_collection(span_exporter, qdrant):
    """Test qdrant.upload_collection operation."""
    upload_collection(qdrant)

    spans = span_exporter.get_finished_spans()
    upload_spans = [span for span in spans if "upload" in span.name]

    if upload_spans:
        span = upload_spans[0]
        assert span.kind == SpanKind.CLIENT
        assert span.attributes.get(QdrantAttributes.COLLECTION_NAME) == COLLECTION_NAME


def query(qdrant: QdrantClient):
    """Perform a query operation."""
    qdrant.query_points(COLLECTION_NAME, query=[0.1] * EMBEDDING_DIM, limit=1)


def test_qdrant_query(span_exporter, qdrant):
    """Test qdrant.query_points operation."""
    upload_collection(qdrant)
    query(qdrant)

    spans = span_exporter.get_finished_spans()
    query_spans = [span for span in spans if "query" in span.name]

    if query_spans:
        span = query_spans[0]
        assert span.kind == SpanKind.CLIENT
        assert span.attributes.get(QdrantAttributes.COLLECTION_NAME) == COLLECTION_NAME


def query_batch(qdrant: QdrantClient):
    """Perform a batch query operation."""
    qdrant.query_batch_points(
        COLLECTION_NAME,
        requests=[
            models.QueryRequest(query=[0.1] * EMBEDDING_DIM, limit=10),
            models.QueryRequest(query=[0.2] * EMBEDDING_DIM, limit=5),
        ],
    )


def test_qdrant_query_batch(span_exporter, qdrant):
    """Test qdrant.query_batch_points operation."""
    upload_collection(qdrant)
    query_batch(qdrant)

    spans = span_exporter.get_finished_spans()
    batch_spans = [span for span in spans if "query_batch" in span.name]

    if batch_spans:
        span = batch_spans[0]
        assert span.kind == SpanKind.CLIENT
        assert span.attributes.get(QdrantAttributes.COLLECTION_NAME) == COLLECTION_NAME
