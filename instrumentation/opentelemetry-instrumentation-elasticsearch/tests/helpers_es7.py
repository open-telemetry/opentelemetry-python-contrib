from elasticsearch_dsl import (  # pylint: disable=unused-import
    Document,
    Keyword,
    Text,
)


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

perform_request_mock_path = "elasticsearch.connection.http_urllib3.Urllib3HttpConnection.perform_request"


def mock_response(body: str, status_code: int = 200):
    return (status_code, {}, body)
