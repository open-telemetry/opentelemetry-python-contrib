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

"""Tests for ChromaDB instrumentation."""

import json
import tempfile

import chromadb
import pytest
from opentelemetry.instrumentation.chromadb.semconv import (
    ChromaDBAttributes,
    EventAttributes,
    Events,
)


@pytest.fixture
def chroma_client():
    """Create a temporary ChromaDB client for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        client = chromadb.PersistentClient(path=tmpdir)
        yield client


@pytest.fixture
def collection(chroma_client):
    """Create and cleanup a test collection."""
    coll = chroma_client.create_collection(name="Students")
    yield coll
    chroma_client.delete_collection(name="Students")


def add_documents(collection, with_metadata=False):
    """Add test documents to the collection."""
    student_info = """
    Alexandra Thompson, a 19-year-old computer science sophomore with a 3.7 GPA,
    is a member of the programming and chess clubs who enjoys pizza, swimming, and hiking
    in her free time in hopes of working at a tech company after graduating from the University of Washington.
    """

    club_info = """
    The university chess club provides an outlet for students to come together and enjoy playing
    the classic strategy game of chess. Members of all skill levels are welcome, from beginners learning
    the rules to experienced tournament players. The club typically meets a few times per week to play casual games,
    participate in tournaments, analyze famous chess matches, and improve members' skills.
    """

    university_info = """
    The University of Washington, founded in 1861 in Seattle, is a public research university
    with over 45,000 students across three campuses in Seattle, Tacoma, and Bothell.
    As the flagship institution of the six public universities in Washington state,
    UW encompasses over 500 buildings and 20 million square feet of space,
    including one of the largest library systems in the world."""

    if with_metadata:
        collection.add(
            documents=[student_info, club_info, university_info],
            metadatas=[
                {"source": "student info"},
                {"source": "club info"},
                {"source": "university info"},
            ],
            ids=["id1", "id2", "id3"],
        )
    else:
        collection.add(
            documents=[student_info, club_info, university_info],
            ids=["id1", "id2", "id3"],
        )


def test_chroma_add(exporter, collection):
    """Test chroma.add operation instrumentation."""
    add_documents(collection, with_metadata=True)

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "chroma.add")

    assert span.attributes.get("db.system") == "chromadb"
    assert span.attributes.get("db.operation") == "add"
    assert span.attributes.get(ChromaDBAttributes.ADD_IDS_COUNT) == 3
    assert span.attributes.get(ChromaDBAttributes.ADD_METADATAS_COUNT) == 3
    assert span.attributes.get(ChromaDBAttributes.ADD_DOCUMENTS_COUNT) == 3


def test_chroma_query(exporter, collection):
    """Test chroma.query operation instrumentation."""
    add_documents(collection)
    collection.query(
        query_texts=["What is the student name?"],
        n_results=2,
    )

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "chroma.query")

    assert span.attributes.get("db.system") == "chromadb"
    assert span.attributes.get("db.operation") == "query"
    assert span.attributes.get(ChromaDBAttributes.QUERY_TEXTS_COUNT) == 1
    assert span.attributes.get(ChromaDBAttributes.QUERY_N_RESULTS) == 2

    events = span.events
    assert len(events) >= 1
    for event in events:
        if event.name == Events.DB_QUERY_RESULT:
            ids_ = event.attributes.get(EventAttributes.DB_QUERY_RESULT_ID)
            distance = event.attributes.get(EventAttributes.DB_QUERY_RESULT_DISTANCE)
            document = event.attributes.get(EventAttributes.DB_QUERY_RESULT_DOCUMENT)

            assert len(ids_) > 0
            assert isinstance(ids_, str)
            assert distance >= 0
            assert len(document) > 0
            assert isinstance(document, str)


def test_chroma_query_with_metadata(exporter, collection):
    """Test chroma.query with metadata filter."""
    add_documents(collection, with_metadata=True)
    collection.query(
        query_texts=["What is the student name?"],
        n_results=2,
        where={"source": "student info"},
    )

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "chroma.query")

    assert span.attributes.get("db.system") == "chromadb"
    assert span.attributes.get("db.operation") == "query"
    assert span.attributes.get(ChromaDBAttributes.QUERY_TEXTS_COUNT) == 1
    assert span.attributes.get(ChromaDBAttributes.QUERY_N_RESULTS) == 2
    assert (
        span.attributes.get(ChromaDBAttributes.QUERY_WHERE)
        == "{'source': 'student info'}"
    )


def test_chroma_get(exporter, collection):
    """Test chroma.get operation instrumentation."""
    add_documents(collection)
    collection.get(ids=["id1", "id2"])

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "chroma.get")

    assert span.attributes.get("db.system") == "chromadb"
    assert span.attributes.get("db.operation") == "get"
    assert span.attributes.get(ChromaDBAttributes.GET_IDS_COUNT) == 2


def test_chroma_update(exporter, collection):
    """Test chroma.update operation instrumentation."""
    add_documents(collection)
    collection.update(
        ids=["id1"],
        documents=["Updated document content"],
    )

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "chroma.update")

    assert span.attributes.get("db.system") == "chromadb"
    assert span.attributes.get("db.operation") == "update"
    assert span.attributes.get(ChromaDBAttributes.UPDATE_IDS_COUNT) == 1
    assert span.attributes.get(ChromaDBAttributes.UPDATE_DOCUMENTS_COUNT) == 1


def test_chroma_delete(exporter, collection):
    """Test chroma.delete operation instrumentation."""
    add_documents(collection)
    collection.delete(ids=["id1"])

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "chroma.delete")

    assert span.attributes.get("db.system") == "chromadb"
    assert span.attributes.get("db.operation") == "delete"
    assert span.attributes.get(ChromaDBAttributes.DELETE_IDS_COUNT) == 1
