# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import Any

import pytest

from opentelemetry._telemetry_policy import (
    Exists,
    LogTarget,
    Regex,
    SpanAttribute,
    TraceField,
    TraceTarget,
)
from opentelemetry._telemetry_policy.parser import parse_policy_document

_SAMPLING_POLICY: dict[str, Any] = {
    "id": "sample-database-spans-5-percent",
    "name": "Sample database spans at 5%",
    "description": "Aggressively samples database spans.",
    "trace": {
        "match": [{"span_attribute": ["db.system"], "exists": True}],
        "keep": {"percentage": 5.0},
    },
}


def _document(*policies: dict[str, Any]) -> str:
    return json.dumps({"policies": list(policies)})


def test_parse_policy() -> None:
    result = parse_policy_document(_document(_SAMPLING_POLICY))

    assert not result.errors
    assert len(result.policies) == 1
    policy = result.policies[0]
    assert policy.id == "sample-database-spans-5-percent"
    assert policy.name == "Sample database spans at 5%"
    assert policy.description == "Aggressively samples database spans."
    assert policy.enabled is True
    assert policy.target_type == "trace"
    assert isinstance(policy.target, TraceTarget)
    assert policy.target.keep.percentage == 5.0
    assert len(policy.target.match) == 1
    matcher = policy.target.match[0]
    assert matcher.field == SpanAttribute(("db.system",))
    assert matcher.match == Exists(True)
    assert matcher.negate is False
    assert matcher.case_insensitive is False


def test_parse_full_sampling_config_and_matcher_options() -> None:
    document = {
        "id": "p1",
        "name": "p1",
        "enabled": False,
        "created_at_unix_nano": 123,
        "modified_at_unix_nano": 456,
        "trace": {
            "match": [
                {
                    "span_attribute": ["http.route"],
                    "regex": "^/health",
                    "negate": True,
                    "case_insensitive": True,
                }
            ],
            "keep": {
                "percentage": 25,
                "mode": "equalizing",
                "sampling_precision": 6,
                "hash_seed": 7,
                "fail_closed": True,
            },
        },
    }

    result = parse_policy_document(_document(document))

    assert not result.errors
    policy = result.policies[0]
    assert policy.enabled is False
    assert policy.created_at_unix_nano == 123
    assert policy.modified_at_unix_nano == 456
    assert isinstance(policy.target, TraceTarget)
    keep = policy.target.keep
    assert keep.percentage == 25.0
    assert keep.mode == "equalizing"
    assert keep.sampling_precision == 6
    assert keep.hash_seed == 7
    assert keep.fail_closed is True
    matcher = policy.target.match[0]
    assert matcher.match == Regex("^/health")
    assert matcher.negate is True
    assert matcher.case_insensitive is True


def test_invalid_policy_is_skipped_and_others_parse() -> None:
    invalid = {"id": "missing-name", "trace": _SAMPLING_POLICY["trace"]}
    result = parse_policy_document(_document(invalid, _SAMPLING_POLICY))

    assert len(result.policies) == 1
    assert result.policies[0].id == "sample-database-spans-5-percent"
    assert len(result.errors) == 1
    assert result.errors[0].policy_id == "missing-name"
    assert "'name'" in result.errors[0].message


@pytest.mark.parametrize(
    "mutation,expected_message_part",
    [
        ({"id": ""}, "'id'"),
        ({"enabled": "yes"}, "'enabled'"),
        ({"trace": None, "log": {}, "metric": {}}, "exactly one target"),
        ({"trace": {"keep": {"percentage": 5.0}}}, "'trace.match'"),
        ({"trace": {"match": [], "keep": {"percentage": 5.0}}}, "'trace.match'"),
        (
            {"trace": {"match": [{"exists": True}], "keep": {"percentage": 5.0}}},
            "exactly one field",
        ),
        (
            {
                "trace": {
                    "match": [{"span_attribute": ["a"]}],
                    "keep": {"percentage": 5.0},
                }
            },
            "exactly one match",
        ),
        (
            {
                "trace": {
                    "match": [{"span_attribute": ["a"], "exists": True, "exact": "b"}],
                    "keep": {"percentage": 5.0},
                }
            },
            "exactly one match",
        ),
        (
            {
                "trace": {
                    "match": [{"span_attribute": "a", "exists": True}],
                    "keep": {"percentage": 5.0},
                }
            },
            "array of strings",
        ),
        (
            {"trace": {"match": [{"span_attribute": ["a"], "exists": True}]}},
            "'trace.keep'",
        ),
        (
            {
                "trace": {
                    "match": [{"span_attribute": ["a"], "exists": True}],
                    "keep": {"percentage": 101},
                }
            },
            "[0, 100]",
        ),
        (
            {
                "trace": {
                    "match": [{"span_attribute": ["a"], "exists": True}],
                    "keep": {"percentage": True},
                }
            },
            "must be a number",
        ),
    ],
)
def test_invalid_policies_report_errors(mutation: dict[str, Any], expected_message_part: str) -> None:
    document = {"id": "p1", "name": "p1", "trace": _SAMPLING_POLICY["trace"]}
    document.update(mutation)
    document = {key: value for key, value in document.items() if value is not None}

    result = parse_policy_document(_document(document))

    assert not result.policies
    assert len(result.errors) == 1
    assert expected_message_part in result.errors[0].message


def test_parse_full_message_with_protobuf_json_encodings() -> None:
    document = {
        "id": "trace-sampling",
        "name": "Trace sampling rate",
        "description": "Set the global trace sampling rate to 10%.",
        "enabled": True,
        "created_at_unix_nano": "1718890000000000000",
        "modified_at_unix_nano": "1718893600000000000",
        "labels": [{"key": "policy.scope", "value": {"string_value": "global"}}],
        "trace": {
            "match": [
                {
                    "trace_field": "trace_id",
                    "exists": True,
                    "negate": False,
                    "case_insensitive": False,
                }
            ],
            "keep": {
                "percentage": "10.0",
                "mode": "proportional",
                "sampling_precision": 6,
                "hash_seed": 0,
                "fail_closed": False,
            },
        },
    }

    result = parse_policy_document(_document(document))

    assert not result.errors
    policy = result.policies[0]
    assert policy.created_at_unix_nano == 1718890000000000000
    assert policy.modified_at_unix_nano == 1718893600000000000
    assert isinstance(policy.target, TraceTarget)
    assert policy.target.keep.percentage == 10.0
    matcher = policy.target.match[0]
    assert matcher.field == TraceField("trace_id")


@pytest.mark.parametrize(
    "keep",
    [
        {},
        {"probability": 0.1},
        {"percentage": "nope"},
    ],
)
def test_invalid_keep_values(keep: dict[str, Any]) -> None:
    document = {
        "id": "p1",
        "name": "p1",
        "trace": {"match": [{"trace_field": "trace_id", "exists": True}], "keep": keep},
    }

    result = parse_policy_document(_document(document))

    assert not result.policies
    assert len(result.errors) == 1


def test_unimplemented_targets_parse_without_trace() -> None:
    document = {
        "id": "drop-debug-logs",
        "name": "Drop debug and trace logs",
        "log": {
            "match": [{"log_field": "severity_text", "regex": "^(DEBUG|TRACE)$"}],
            "keep": "none",
        },
    }

    result = parse_policy_document(_document(document))

    assert not result.errors
    policy = result.policies[0]
    assert policy.target_type == "log"
    assert policy.target == LogTarget()


def test_profile_target_recognized() -> None:
    document = {"id": "p1", "name": "p1", "profile": {"anything": True}}

    result = parse_policy_document(_document(document))

    assert not result.errors
    assert result.policies[0].target_type == "profile"


def test_invalid_documents_raise_value_error() -> None:
    for document in (
        "not json",
        '"a string"',
        json.dumps({"policies": "nope"}),
        json.dumps(_SAMPLING_POLICY),
        json.dumps([_SAMPLING_POLICY]),
    ):
        with pytest.raises(ValueError):
            parse_policy_document(document)
