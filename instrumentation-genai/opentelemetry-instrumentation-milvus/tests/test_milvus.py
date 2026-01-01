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

"""Tests for Milvus instrumentation."""

import os
import random
import sys
import tempfile

import pymilvus
import pytest

# Skip all tests on non-Linux platforms as milvus-lite is only available on Linux
pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="milvus-lite is only available on Linux",
)
from opentelemetry.instrumentation.milvus.semconv import (
    EventAttributes,
    Events,
    Meters,
    MilvusAttributes,
)
from opentelemetry.trace.status import StatusCode


def find_metrics_by_name(metrics_data, target_name):
    """Return a list of metrics with the given name from the reader."""
    matching_metrics = []
    for rm in metrics_data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == target_name:
                    matching_metrics.append(metric)
    return matching_metrics


@pytest.fixture
def milvus_client():
    """Create a temporary Milvus client for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "milvus.db")
        client = pymilvus.MilvusClient(uri=db_path)
        yield client


@pytest.fixture
def collection(milvus_client):
    """Create and cleanup a test collection."""
    collection_name = "Colors"
    milvus_client.create_collection(collection_name=collection_name, dimension=5)
    yield collection_name
    milvus_client.drop_collection(collection_name=collection_name)


def insert_data(milvus_client, collection):
    """Insert test data into the collection."""
    colors = [
        "green",
        "blue",
        "yellow",
        "red",
        "black",
        "white",
        "purple",
        "pink",
        "orange",
        "grey",
    ]
    data = [
        {
            "id": i,
            "vector": [random.uniform(-1, 1) for _ in range(5)],
            "color": random.choice(colors),
            "tag": random.randint(1000, 9999),
        }
        for i in range(100)
    ]
    data += [
        {
            "id": 100,
            "vector": [random.uniform(-1, 1) for _ in range(5)],
            "color": "brown",
            "tag": 1234,
        },
        {
            "id": 101,
            "vector": [random.uniform(-1, 1) for _ in range(5)],
            "color": "brown",
            "tag": 5678,
        },
        {
            "id": 102,
            "vector": [random.uniform(-1, 1) for _ in range(5)],
            "color": "brown",
            "tag": 9101,
        },
    ]
    for i in data:
        i["color_tag"] = "{}_{}".format(i["color"], i["tag"])
    milvus_client.insert(collection_name=collection, data=data)


def test_milvus_insert(exporter, reader, milvus_client, collection):
    """Test milvus.insert operation instrumentation."""
    insert_data(milvus_client, collection)

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "milvus.insert")

    assert span.attributes.get("db.system") == "milvus"
    assert span.attributes.get("db.operation") == "insert"
    assert span.attributes.get(MilvusAttributes.INSERT_COLLECTION_NAME) == "Colors"
    assert span.attributes.get(MilvusAttributes.INSERT_DATA_COUNT) == 103

    metrics_data = reader.get_metrics_data()
    insert_metrics = find_metrics_by_name(metrics_data, Meters.USAGE_INSERT_UNITS)
    for metric in insert_metrics:
        assert all(dp.value == 103 for dp in metric.data.data_points)


def test_milvus_search(exporter, reader, milvus_client, collection):
    """Test milvus.search operation instrumentation."""
    insert_data(milvus_client, collection)

    query_vectors = [
        [random.uniform(-1, 1) for _ in range(5)],
    ]
    search_params = {"radius": 0.5, "metric_type": "COSINE", "index_type": "IVF_FLAT"}
    milvus_client.search(
        collection_name=collection,
        data=query_vectors,
        anns_field="vector",
        search_params=search_params,
        output_fields=["color_tag"],
        limit=3,
        timeout=10,
    )

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "milvus.search")

    assert span.attributes.get("db.system") == "milvus"
    assert span.attributes.get("db.operation") == "search"
    assert span.attributes.get(MilvusAttributes.SEARCH_COLLECTION_NAME) == collection
    assert span.attributes.get(MilvusAttributes.SEARCH_OUTPUT_FIELDS_COUNT) == 1
    assert span.attributes.get(MilvusAttributes.SEARCH_LIMIT) == 3
    assert span.attributes.get(MilvusAttributes.SEARCH_TIMEOUT) == 10
    assert span.attributes.get(MilvusAttributes.SEARCH_ANNS_FIELD) == "vector"

    events = span.events
    for event in events:
        if event.name == Events.DB_SEARCH_RESULT:
            _id = event.attributes.get(EventAttributes.DB_SEARCH_RESULT_ID)
            distance = event.attributes.get(EventAttributes.DB_SEARCH_RESULT_DISTANCE)
            assert isinstance(_id, int)
            assert isinstance(distance, str)


def test_milvus_query(exporter, reader, milvus_client, collection):
    """Test milvus.query operation instrumentation."""
    insert_data(milvus_client, collection)
    milvus_client.query(
        collection_name=collection,
        filter='color == "brown"',
        output_fields=["color_tag"],
        limit=3,
    )

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "milvus.query")

    assert span.attributes.get("db.system") == "milvus"
    assert span.attributes.get("db.operation") == "query"
    assert span.attributes.get(MilvusAttributes.QUERY_COLLECTION_NAME) == collection
    assert span.attributes.get(MilvusAttributes.QUERY_FILTER) == 'color == "brown"'
    assert span.attributes.get(MilvusAttributes.QUERY_OUTPUT_FIELDS_COUNT) == 1
    assert span.attributes.get(MilvusAttributes.QUERY_LIMIT) == 3

    metrics_data = reader.get_metrics_data()
    duration_metrics = find_metrics_by_name(metrics_data, Meters.QUERY_DURATION)
    for metric in duration_metrics:
        assert all(dp.sum >= 0 for dp in metric.data.data_points)


def test_milvus_get(exporter, milvus_client, collection):
    """Test milvus.get operation instrumentation."""
    insert_data(milvus_client, collection)
    milvus_client.get(
        collection_name=collection,
        ids=[100, 101, 102],
        output_fields=["color_tag"],
        timeout=10,
    )

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "milvus.get")

    assert span.attributes.get("db.system") == "milvus"
    assert span.attributes.get("db.operation") == "get"
    assert span.attributes.get(MilvusAttributes.GET_COLLECTION_NAME) == collection
    assert span.attributes.get(MilvusAttributes.GET_OUTPUT_FIELDS_COUNT) == 1
    assert span.attributes.get(MilvusAttributes.GET_TIMEOUT) == 10
    assert span.attributes.get(MilvusAttributes.GET_IDS_COUNT) == 3


def test_milvus_delete(exporter, reader, milvus_client, collection):
    """Test milvus.delete operation instrumentation."""
    insert_data(milvus_client, collection)
    milvus_client.delete(collection_name=collection, ids=[100, 101, 102], timeout=10)

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "milvus.delete")

    assert span.attributes.get("db.system") == "milvus"
    assert span.attributes.get("db.operation") == "delete"
    assert span.attributes.get(MilvusAttributes.DELETE_COLLECTION_NAME) == collection
    assert span.attributes.get(MilvusAttributes.DELETE_IDS_COUNT) == 3
    assert span.attributes.get(MilvusAttributes.DELETE_TIMEOUT) == 10

    metrics_data = reader.get_metrics_data()
    delete_metrics = find_metrics_by_name(metrics_data, Meters.USAGE_DELETE_UNITS)
    for metric in delete_metrics:
        assert all(dp.value == 3 for dp in metric.data.data_points)


def test_milvus_upsert(exporter, reader, milvus_client, collection):
    """Test milvus.upsert operation instrumentation."""
    insert_data(milvus_client, collection)
    modified_data = {
        "id": 100,
        "vector": [random.uniform(-1, 1) for _ in range(5)],
        "color": "red",
        "tag": 1234,
    }
    milvus_client.upsert(collection_name=collection, data=modified_data)

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "milvus.upsert")

    assert span.attributes.get("db.system") == "milvus"
    assert span.attributes.get("db.operation") == "upsert"
    assert span.attributes.get(MilvusAttributes.UPSERT_COLLECTION_NAME) == "Colors"

    metrics_data = reader.get_metrics_data()
    upsert_metrics = find_metrics_by_name(metrics_data, Meters.USAGE_UPSERT_UNITS)
    for metric in upsert_metrics:
        assert all(dp.value == 1 for dp in metric.data.data_points)


def test_milvus_search_error(exporter, milvus_client, collection):
    """Test milvus.search error handling."""
    insert_data(milvus_client, collection)

    query_vector = [random.uniform(-1, 1) for _ in range(5)]
    search_params = {"radius": 0.5, "metric_type": "COSINE", "index_type": "IVF_FLAT"}
    with pytest.raises(Exception):
        milvus_client.search(
            collection_name="nonexistent_collection",
            data=[query_vector],
            anns_field="vector",
            search_params=search_params,
            output_fields=["color_tag"],
            limit=3,
            timeout=10,
        )

    spans = exporter.get_finished_spans()
    span = next(span for span in spans if span.name == "milvus.search")

    assert span.status.status_code == StatusCode.ERROR
