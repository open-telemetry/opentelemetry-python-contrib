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

"""Semantic conventions for LanceDB instrumentation."""


class LanceDBAttributes:
    """LanceDB-specific span attributes."""

    # Add operation
    ADD_DATA_COUNT = "db.lancedb.add.data_count"

    # Search operation
    SEARCH_QUERY = "db.lancedb.search.query"
    SEARCH_LIMIT = "db.lancedb.search.limit"

    # Delete operation
    DELETE_WHERE = "db.lancedb.delete.where"
