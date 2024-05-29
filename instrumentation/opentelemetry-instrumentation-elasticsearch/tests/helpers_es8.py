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
                "analyzer": "snowball",
                "fields": {"raw": {"type": "keyword"}},
                "type": "text",
            },
            "body": {"analyzer": "snowball", "type": "text"},
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
