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

"""Method definitions for Qdrant instrumentation."""

# Sync QdrantClient methods
QDRANT_CLIENT_METHODS = [
    {"object": "QdrantClient", "method": "upsert", "span_name": "qdrant.upsert"},
    {"object": "QdrantClient", "method": "add", "span_name": "qdrant.add"},
    {"object": "QdrantClient", "method": "upload_points", "span_name": "qdrant.upload_points"},
    {"object": "QdrantClient", "method": "upload_records", "span_name": "qdrant.upload_records"},
    {"object": "QdrantClient", "method": "upload_collection", "span_name": "qdrant.upload_collection"},
    {"object": "QdrantClient", "method": "search", "span_name": "qdrant.search"},
    {"object": "QdrantClient", "method": "search_batch", "span_name": "qdrant.search_batch"},
    {"object": "QdrantClient", "method": "search_groups", "span_name": "qdrant.search_groups"},
    {"object": "QdrantClient", "method": "query", "span_name": "qdrant.query"},
    {"object": "QdrantClient", "method": "query_batch", "span_name": "qdrant.query_batch"},
    {"object": "QdrantClient", "method": "discover", "span_name": "qdrant.discover"},
    {"object": "QdrantClient", "method": "discover_batch", "span_name": "qdrant.discover_batch"},
    {"object": "QdrantClient", "method": "recommend", "span_name": "qdrant.recommend"},
    {"object": "QdrantClient", "method": "recommend_batch", "span_name": "qdrant.recommend_batch"},
    {"object": "QdrantClient", "method": "recommend_groups", "span_name": "qdrant.recommend_groups"},
    {"object": "QdrantClient", "method": "scroll", "span_name": "qdrant.scroll"},
    {"object": "QdrantClient", "method": "delete", "span_name": "qdrant.delete"},
    {"object": "QdrantClient", "method": "delete_vectors", "span_name": "qdrant.delete_vectors"},
    {"object": "QdrantClient", "method": "delete_payload", "span_name": "qdrant.delete_payload"},
    {"object": "QdrantClient", "method": "set_payload", "span_name": "qdrant.set_payload"},
    {"object": "QdrantClient", "method": "overwrite_payload", "span_name": "qdrant.overwrite_payload"},
    {"object": "QdrantClient", "method": "update_vectors", "span_name": "qdrant.update_vectors"},
    {"object": "QdrantClient", "method": "batch_update_points", "span_name": "qdrant.batch_update_points"},
]

# Async AsyncQdrantClient methods
ASYNC_QDRANT_CLIENT_METHODS = [
    {"object": "AsyncQdrantClient", "method": "upsert", "span_name": "qdrant.upsert"},
    {"object": "AsyncQdrantClient", "method": "add", "span_name": "qdrant.add"},
    {"object": "AsyncQdrantClient", "method": "upload_points", "span_name": "qdrant.upload_points"},
    {"object": "AsyncQdrantClient", "method": "upload_records", "span_name": "qdrant.upload_records"},
    {"object": "AsyncQdrantClient", "method": "upload_collection", "span_name": "qdrant.upload_collection"},
    {"object": "AsyncQdrantClient", "method": "search", "span_name": "qdrant.search"},
    {"object": "AsyncQdrantClient", "method": "search_batch", "span_name": "qdrant.search_batch"},
    {"object": "AsyncQdrantClient", "method": "search_groups", "span_name": "qdrant.search_groups"},
    {"object": "AsyncQdrantClient", "method": "query", "span_name": "qdrant.query"},
    {"object": "AsyncQdrantClient", "method": "query_batch", "span_name": "qdrant.query_batch"},
    {"object": "AsyncQdrantClient", "method": "discover", "span_name": "qdrant.discover"},
    {"object": "AsyncQdrantClient", "method": "discover_batch", "span_name": "qdrant.discover_batch"},
    {"object": "AsyncQdrantClient", "method": "recommend", "span_name": "qdrant.recommend"},
    {"object": "AsyncQdrantClient", "method": "recommend_batch", "span_name": "qdrant.recommend_batch"},
    {"object": "AsyncQdrantClient", "method": "recommend_groups", "span_name": "qdrant.recommend_groups"},
    {"object": "AsyncQdrantClient", "method": "scroll", "span_name": "qdrant.scroll"},
    {"object": "AsyncQdrantClient", "method": "delete", "span_name": "qdrant.delete"},
    {"object": "AsyncQdrantClient", "method": "delete_vectors", "span_name": "qdrant.delete_vectors"},
    {"object": "AsyncQdrantClient", "method": "delete_payload", "span_name": "qdrant.delete_payload"},
    {"object": "AsyncQdrantClient", "method": "set_payload", "span_name": "qdrant.set_payload"},
    {"object": "AsyncQdrantClient", "method": "overwrite_payload", "span_name": "qdrant.overwrite_payload"},
    {"object": "AsyncQdrantClient", "method": "update_vectors", "span_name": "qdrant.update_vectors"},
    {"object": "AsyncQdrantClient", "method": "batch_update_points", "span_name": "qdrant.batch_update_points"},
]

# Combined list
WRAPPED_METHODS = QDRANT_CLIENT_METHODS + ASYNC_QDRANT_CLIENT_METHODS
