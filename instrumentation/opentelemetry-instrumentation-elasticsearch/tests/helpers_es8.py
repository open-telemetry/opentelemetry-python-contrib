# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from elastic_transport import ApiResponseMeta, HttpHeaders
from elastic_transport._node import NodeApiResponse
from elasticsearch_dsl import Document, Keyword, Text


class Article(Document):
    title = Text(analyzer="snowball", fields={"raw": Keyword()})
    body = Text(analyzer="snowball")

    class Index:
        name = "test-index"


dsl_create_statement = {
    "mappings": {
        "properties": {
            "title": {
                "analyzer": "?",
                "fields": {"raw": {"type": "?"}},
                "type": "?",
            },
            "body": {"analyzer": "?", "type": "?"},
        }
    }
}
dsl_index_result = (1, {}, '{"result": "created"}')
dsl_index_span_name = "Elasticsearch/test-index/_doc/:id"
dsl_index_url = "/test-index/_doc/2"
dsl_search_method = "POST"

perform_request_mock_path = (
    "elastic_transport._node._http_urllib3.Urllib3HttpNode.perform_request"
)


def mock_response(body: str, status_code: int = 200):
    return NodeApiResponse(
        ApiResponseMeta(
            status=status_code,
            headers=HttpHeaders({}),
            duration=100,
            http_version="1.1",
            node="node",
        ),
        body.encode(),
    )
