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

"""Semantic conventions for Qdrant instrumentation."""


class QdrantAttributes:
    """Qdrant-specific span attributes."""

    # Common
    COLLECTION_NAME = "db.qdrant.collection_name"

    # Upsert operation
    UPSERT_POINTS_COUNT = "db.qdrant.upsert.points_count"

    # Upload operations
    UPLOAD_POINTS_COUNT = "db.qdrant.upload.points_count"

    # Search operations
    SEARCH_LIMIT = "db.qdrant.search.limit"
    SEARCH_BATCH_REQUESTS_COUNT = "db.qdrant.search_batch.requests_count"

    # Query operations
    QUERY_BATCH_REQUESTS_COUNT = "db.qdrant.query_batch.requests_count"

    # Discover operations
    DISCOVER_BATCH_REQUESTS_COUNT = "db.qdrant.discover_batch.requests_count"

    # Recommend operations
    RECOMMEND_BATCH_REQUESTS_COUNT = "db.qdrant.recommend_batch.requests_count"
