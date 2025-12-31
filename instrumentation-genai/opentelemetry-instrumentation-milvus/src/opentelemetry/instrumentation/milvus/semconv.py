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

"""Semantic conventions for Milvus instrumentation."""


class MilvusAttributes:
    """Milvus-specific span attributes."""

    # Create collection operation
    CREATE_COLLECTION_NAME = "db.milvus.create_collection.collection_name"
    CREATE_COLLECTION_DIMENSION = "db.milvus.create_collection.dimension"
    CREATE_COLLECTION_METRIC_TYPE = "db.milvus.create_collection.metric_type"
    CREATE_COLLECTION_PRIMARY_FIELD = "db.milvus.create_collection.primary_field"
    CREATE_COLLECTION_VECTOR_FIELD = "db.milvus.create_collection.vector_field"
    CREATE_COLLECTION_ID_TYPE = "db.milvus.create_collection.id_type"
    CREATE_COLLECTION_TIMEOUT = "db.milvus.create_collection.timeout"

    # Insert operation
    INSERT_COLLECTION_NAME = "db.milvus.insert.collection_name"
    INSERT_DATA_COUNT = "db.milvus.insert.data_count"
    INSERT_PARTITION_NAME = "db.milvus.insert.partition_name"
    INSERT_TIMEOUT = "db.milvus.insert.timeout"

    # Upsert operation
    UPSERT_COLLECTION_NAME = "db.milvus.upsert.collection_name"
    UPSERT_DATA_COUNT = "db.milvus.upsert.data_count"
    UPSERT_PARTITION_NAME = "db.milvus.upsert.partition_name"
    UPSERT_TIMEOUT = "db.milvus.upsert.timeout"

    # Delete operation
    DELETE_COLLECTION_NAME = "db.milvus.delete.collection_name"
    DELETE_IDS_COUNT = "db.milvus.delete.ids_count"
    DELETE_FILTER = "db.milvus.delete.filter"
    DELETE_PARTITION_NAME = "db.milvus.delete.partition_name"
    DELETE_TIMEOUT = "db.milvus.delete.timeout"

    # Search operation
    SEARCH_COLLECTION_NAME = "db.milvus.search.collection_name"
    SEARCH_DATA_COUNT = "db.milvus.search.data_count"
    SEARCH_FILTER = "db.milvus.search.filter"
    SEARCH_LIMIT = "db.milvus.search.limit"
    SEARCH_OUTPUT_FIELDS_COUNT = "db.milvus.search.output_fields_count"
    SEARCH_PARAMS = "db.milvus.search.search_params"
    SEARCH_TIMEOUT = "db.milvus.search.timeout"
    SEARCH_PARTITION_NAMES = "db.milvus.search.partition_names"
    SEARCH_PARTITION_NAMES_COUNT = "db.milvus.search.partition_names_count"
    SEARCH_ANNS_FIELD = "db.milvus.search.anns_field"
    SEARCH_QUERY_VECTOR_DIMENSION = "db.milvus.search.query_vector_dimension"
    SEARCH_RESULT_COUNT = "db.milvus.search.result_count"
    SEARCH_ANNSEARCH_REQUEST = "db.milvus.search.annsearch_request"
    SEARCH_RANKER_TYPE = "db.milvus.search.ranker_type"

    # Get operation
    GET_COLLECTION_NAME = "db.milvus.get.collection_name"
    GET_IDS_COUNT = "db.milvus.get.ids_count"
    GET_OUTPUT_FIELDS_COUNT = "db.milvus.get.output_fields_count"
    GET_TIMEOUT = "db.milvus.get.timeout"
    GET_PARTITION_NAMES_COUNT = "db.milvus.get.partition_names_count"

    # Query operation
    QUERY_COLLECTION_NAME = "db.milvus.query.collection_name"
    QUERY_FILTER = "db.milvus.query.filter"
    QUERY_OUTPUT_FIELDS_COUNT = "db.milvus.query.output_fields_count"
    QUERY_TIMEOUT = "db.milvus.query.timeout"
    QUERY_IDS_COUNT = "db.milvus.query.ids_count"
    QUERY_PARTITION_NAMES_COUNT = "db.milvus.query.partition_names_count"
    QUERY_LIMIT = "db.milvus.query.limit"


class Events:
    """Event names for Milvus instrumentation."""

    DB_QUERY_RESULT = "db.query.result"
    DB_SEARCH_RESULT = "db.search.result"


class EventAttributes:
    """Event attributes for Milvus instrumentation."""

    DB_SEARCH_RESULT_QUERY_ID = "db.search.result.query_id"
    DB_SEARCH_RESULT_ID = "db.search.result.id"
    DB_SEARCH_RESULT_DISTANCE = "db.search.result.distance"
    DB_SEARCH_RESULT_ENTITY = "db.search.result.entity"


class Meters:
    """Meter names for Milvus instrumentation."""

    QUERY_DURATION = "db.milvus.query.duration"
    SEARCH_DISTANCE = "db.milvus.search.distance"
    USAGE_INSERT_UNITS = "db.milvus.usage.insert_units"
    USAGE_UPSERT_UNITS = "db.milvus.usage.upsert_units"
    USAGE_DELETE_UNITS = "db.milvus.usage.delete_units"
