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

"""Semantic conventions for Pinecone instrumentation."""


class PineconeAttributes:
    """Pinecone-specific span attributes."""

    # Query operation
    QUERY_TOP_K = "db.pinecone.query.top_k"
    QUERY_NAMESPACE = "db.pinecone.query.namespace"
    QUERY_FILTER = "db.pinecone.query.filter"
    QUERY_ID = "db.pinecone.query.id"
    QUERY_INCLUDE_VALUES = "db.pinecone.query.include_values"
    QUERY_INCLUDE_METADATA = "db.pinecone.query.include_metadata"

    # Usage
    USAGE_READ_UNITS = "db.pinecone.usage.read_units"
    USAGE_WRITE_UNITS = "db.pinecone.usage.write_units"


class Events:
    """Event names for Pinecone instrumentation."""

    DB_QUERY_EMBEDDINGS = "db.query.embeddings"
    DB_QUERY_RESULT = "db.query.result"


class EventAttributes:
    """Event attributes for Pinecone instrumentation."""

    DB_QUERY_EMBEDDINGS_VECTOR = "db.query.embeddings.vector"
    DB_QUERY_RESULT_ID = "db.query.result.id"
    DB_QUERY_RESULT_SCORE = "db.query.result.score"
    DB_QUERY_RESULT_METADATA = "db.query.result.metadata"
    DB_QUERY_RESULT_VECTOR = "db.query.result.vector"


class Meters:
    """Meter names for Pinecone instrumentation."""

    QUERY_DURATION = "db.pinecone.query.duration"
    QUERY_SCORES = "db.pinecone.query.scores"
    USAGE_READ_UNITS = "db.pinecone.usage.read_units"
    USAGE_WRITE_UNITS = "db.pinecone.usage.write_units"
