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

"""Semantic conventions for ChromaDB instrumentation."""


class ChromaDBAttributes:
    """ChromaDB-specific span attributes."""

    # Add operation
    ADD_IDS_COUNT = "db.chroma.add.ids_count"
    ADD_EMBEDDINGS_COUNT = "db.chroma.add.embeddings_count"
    ADD_METADATAS_COUNT = "db.chroma.add.metadatas_count"
    ADD_DOCUMENTS_COUNT = "db.chroma.add.documents_count"

    # Get operation
    GET_IDS_COUNT = "db.chroma.get.ids_count"
    GET_WHERE = "db.chroma.get.where"
    GET_LIMIT = "db.chroma.get.limit"
    GET_OFFSET = "db.chroma.get.offset"
    GET_WHERE_DOCUMENT = "db.chroma.get.where_document"
    GET_INCLUDE = "db.chroma.get.include"

    # Query operation
    QUERY_EMBEDDINGS_COUNT = "db.chroma.query.embeddings_count"
    QUERY_TEXTS_COUNT = "db.chroma.query.texts_count"
    QUERY_N_RESULTS = "db.chroma.query.n_results"
    QUERY_WHERE = "db.chroma.query.where"
    QUERY_WHERE_DOCUMENT = "db.chroma.query.where_document"
    QUERY_INCLUDE = "db.chroma.query.include"
    QUERY_SEGMENT_COLLECTION_ID = "db.chroma.query.segment._query.collection_id"

    # Peek operation
    PEEK_LIMIT = "db.chroma.peek.limit"

    # Update operation
    UPDATE_IDS_COUNT = "db.chroma.update.ids_count"
    UPDATE_EMBEDDINGS_COUNT = "db.chroma.update.embeddings_count"
    UPDATE_METADATAS_COUNT = "db.chroma.update.metadatas_count"
    UPDATE_DOCUMENTS_COUNT = "db.chroma.update.documents_count"

    # Upsert operation
    UPSERT_EMBEDDINGS_COUNT = "db.chroma.upsert.embeddings_count"
    UPSERT_METADATAS_COUNT = "db.chroma.upsert.metadatas_count"
    UPSERT_DOCUMENTS_COUNT = "db.chroma.upsert.documents_count"

    # Delete operation
    DELETE_IDS_COUNT = "db.chroma.delete.ids_count"
    DELETE_WHERE = "db.chroma.delete.where"
    DELETE_WHERE_DOCUMENT = "db.chroma.delete.where_document"

    # Modify operation
    MODIFY_NAME = "db.chroma.modify.name"


class Events:
    """Event names for ChromaDB instrumentation."""

    DB_QUERY_EMBEDDINGS = "db.query.embeddings"
    DB_QUERY_RESULT = "db.query.result"


class EventAttributes:
    """Event attribute names for ChromaDB instrumentation."""

    DB_QUERY_EMBEDDINGS_VECTOR = "db.query.embeddings.vector"
    DB_QUERY_RESULT_ID = "db.query.result.id"
    DB_QUERY_RESULT_DISTANCE = "db.query.result.distance"
    DB_QUERY_RESULT_METADATA = "db.query.result.metadata"
    DB_QUERY_RESULT_DOCUMENT = "db.query.result.document"
