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

"""Semantic conventions for Marqo instrumentation."""


class MarqoAttributes:
    """Marqo-specific span attributes."""

    # Add documents operation
    ADD_DOCUMENTS_COUNT = "db.marqo.add_documents.documents_count"

    # Search operation
    SEARCH_QUERY = "db.marqo.search.query"
    SEARCH_PROCESSING_TIME = "db.marqo.search.processing_time"

    # Delete documents operation
    DELETE_IDS_COUNT = "db.marqo.delete_documents.ids_count"
    DELETE_STATUS = "db.marqo.delete_documents.status"


class Events:
    """Event names for Marqo instrumentation."""

    DB_QUERY_RESULT = "db.query.result"


class EventAttributes:
    """Event attributes for Marqo instrumentation."""

    DB_QUERY_RESULT_ID = "db.query.result.id"
    DB_QUERY_RESULT_SCORE = "db.query.result.score"
