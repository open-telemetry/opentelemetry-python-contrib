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

term_query = {
    "query": {
        "bool": {
            "must": [
                {"term": {"user_email": "john.doe@company.com"}},
                {"term": {"ssn": "123-45-6789"}},
                {"term": {"credit_card": "4111-1111-1111-1111"}},
            ]
        }
    }
}

interval_query_sanitized = {
    "query": {
        "intervals": {
            "my_text": {
                "all_of": {
                    "ordered": "?",
                    "intervals": [
                        {
                            "match": {
                                "query": "?",
                                "max_gaps": "?",
                                "ordered": "?",
                            }
                        },
                        {
                            "any_of": {
                                "intervals": [
                                    {"match": {"query": "?"}},
                                    {"match": {"query": "?"}},
                                ]
                            }
                        },
                    ],
                }
            }
        }
    }
}

match_query_sanitized = {"query": {"match": {"message": {"query": "?"}}}}

filter_query_sanitized = {
    "query": {
        "bool": {
            "must": [
                {"match": {"title": "?"}},
                {"match": {"content": "?"}},
            ],
            "filter": [
                {"term": {"status": "?"}},
                {"range": {"publish_date": {"gte": "?"}}},
            ],
        }
    }
}

term_query_sanitized = {
    "query": {
        "bool": {
            "must": [
                {"term": {"user_email": "?"}},
                {"term": {"ssn": "?"}},
                {"term": {"credit_card": "?"}},
            ]
        }
    }
}

aggregation_query = {
    "query": {"match_all": {}},
    "aggs": {
        "price_ranges": {
            "range": {
                "field": "price",
                "ranges": [
                    {"to": 50, "key": "cheap"},
                    {"from": 50, "to": 100, "key": "medium"},
                    {"from": 100, "key": "expensive"},
                ],
            }
        },
        "avg_price": {"avg": {"field": "price"}},
        "top_tags": {
            "terms": {"field": "tags", "size": 10, "order": {"_count": "desc"}}
        },
    },
}

aggregation_query_sanitized = {
    "query": {"match_all": {}},
    "aggs": {
        "price_ranges": {
            "range": {
                "field": "?",
                "ranges": [
                    {"to": "?", "key": "?"},
                    {"from": "?", "to": "?", "key": "?"},
                    {"from": "?", "key": "?"},
                ],
            }
        },
        "avg_price": {"avg": {"field": "?"}},
        "top_tags": {
            "terms": {"field": "?", "size": "?", "order": {"_count": "?"}}
        },
    },
}

script_query = {
    "query": {
        "script": {
            "script": {
                "source": "doc['price'].value > params.threshold",
                "lang": "painless",
                "params": {"threshold": 100},
            }
        }
    },
    "script_fields": {
        "discounted_price": {
            "script": {
                "source": "doc['price'].value * params.discount",
                "params": {"discount": 0.9},
            }
        }
    },
}

script_query_sanitized = {
    "query": {
        "script": {
            "script": {
                "source": "?",
                "lang": "?",
                "params": {"threshold": "?"},
            }
        }
    },
    "script_fields": {
        "discounted_price": {
            "script": {"source": "?", "params": {"discount": "?"}}
        }
    },
}
