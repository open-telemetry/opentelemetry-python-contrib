interval_query = {
    "query": {
        "intervals": {
            "my_text": {
                "all_of": {
                    "ordered": True,
                    "intervals": [
                        {
                            "match": {
                                "query": "my favorite food",
                                "max_gaps": 0,
                                "ordered": True,
                            }
                        },
                        {
                            "any_of": {
                                "intervals": [
                                    {"match": {"query": "hot water"}},
                                    {"match": {"query": "cold porridge"}},
                                ]
                            }
                        },
                    ],
                }
            }
        }
    }
}

match_query = {"query": {"match": {"message": {"query": "this is a test"}}}}

filter_query = {
    "query": {
        "bool": {
            "must": [
                {"match": {"title": "Search"}},
                {"match": {"content": "Elasticsearch"}},
            ],
            "filter": [
                {"term": {"status": "published"}},
                {"range": {"publish_date": {"gte": "2015-01-01"}}},
            ],
        }
    }
}

interval_query_sanitized = {
    "query": {
        "intervals": {
            "my_text": {"all_of": {"ordered": True, "intervals": "?"}}
        }
    }
}
match_query_sanitized = {"query": {"match": {"message": {"query": "?"}}}}
filter_query_sanitized = {
    "query": {
        "bool": {
            "must": [
                {"match": {"title": "Search"}},
                {"match": {"content": "Elasticsearch"}},
            ],
            "filter": "?",
        }
    }
}
