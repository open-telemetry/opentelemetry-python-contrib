# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from opentelemetry._telemetry_policy.model import (
    KNOWN_TARGET_TYPES,
    TARGET_TYPE_LOG,
    TARGET_TYPE_METRIC,
    TARGET_TYPE_PROFILE,
    TARGET_TYPE_TRACE,
    Contains,
    EndsWith,
    EventAttribute,
    EventNameField,
    Exact,
    Exists,
    LinkTraceIdField,
    LogTarget,
    MatchPredicate,
    MetricTarget,
    Policy,
    PolicyTarget,
    ProfileTarget,
    Regex,
    ResourceAttribute,
    ScopeAttribute,
    SpanAttribute,
    SpanKindField,
    SpanStatusField,
    StartsWith,
    TargetType,
    TraceField,
    TraceMatcher,
    TraceMatcherField,
    TraceSamplingConfig,
    TraceTarget,
)

# Parses a policy document. All of the logic in this file should be replaced by parsing using
# a protobuf schema in the future.

_ATTRIBUTE_PATH_FIELD_TYPES: dict[str, Callable[[tuple[str, ...]], TraceMatcherField]] = {
    "span_attribute": SpanAttribute,
    "resource_attribute": ResourceAttribute,
    "scope_attribute": ScopeAttribute,
    "event_attribute": EventAttribute,
}
_STRING_FIELD_TYPES: dict[str, Callable[[str], TraceMatcherField]] = {
    "trace_field": TraceField,
    "span_kind": SpanKindField,
    "span_status": SpanStatusField,
    "event_name": EventNameField,
    "link_trace_id": LinkTraceIdField,
}
_FIELD_KEYS = (*_STRING_FIELD_TYPES, *_ATTRIBUTE_PATH_FIELD_TYPES)

_STRING_MATCH_TYPES: dict[str, Callable[[str], MatchPredicate]] = {
    "exact": Exact,
    "regex": Regex,
    "starts_with": StartsWith,
    "ends_with": EndsWith,
    "contains": Contains,
}
_MATCH_KEYS = (*_STRING_MATCH_TYPES, "exists")

_EMPTY_TARGETS: dict[TargetType, PolicyTarget] = {
    TARGET_TYPE_LOG: LogTarget(),
    TARGET_TYPE_METRIC: MetricTarget(),
    TARGET_TYPE_PROFILE: ProfileTarget(),
}


@dataclass(frozen=True)
class PolicyParseError:
    """A policy that could not be parsed."""

    policy_id: str
    message: str


@dataclass(frozen=True)
class PolicyParseResult:
    policies: tuple[Policy, ...]
    errors: tuple[PolicyParseError, ...]


class _PolicyError(Exception):
    pass


def parse_policy_document(text: str) -> PolicyParseResult:
    """Parse a JSON policy document into policies.

    The document is a JSON object with a ``policies`` array of policy
    objects. Field names follow the telemetry policy schema's snake_case
    JSON form. An invalid policy is skipped and reported in ``errors``.

    Raises:
        ValueError: the document itself is not valid JSON or not one of the
            accepted document shapes. Callers should keep their previous
            policy snapshot in that case.
    """
    try:
        document: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"policy document is not valid JSON: {exc}") from exc

    raw_policies: Any = None
    if isinstance(document, dict):
        raw_policies = cast("dict[str, Any]", document).get("policies")
    if not isinstance(raw_policies, list):
        raise ValueError("policy document must be a JSON object with a 'policies' array")

    policies: list[Policy] = []
    errors: list[PolicyParseError] = []
    for raw_policy in cast("list[Any]", raw_policies):
        if not isinstance(raw_policy, dict):
            errors.append(PolicyParseError(policy_id="", message="policy is not a JSON object"))
            continue
        raw_policy_object = cast("dict[str, Any]", raw_policy)
        raw_id = raw_policy_object.get("id")
        policy_id = raw_id if isinstance(raw_id, str) else ""
        try:
            policies.append(_parse_policy(raw_policy_object))
        except _PolicyError as exc:
            errors.append(PolicyParseError(policy_id=policy_id, message=str(exc)))
    return PolicyParseResult(policies=tuple(policies), errors=tuple(errors))


def _parse_policy(raw: dict[str, Any]) -> Policy:
    policy_id = _required_string(raw, "id")
    name = _required_string(raw, "name")
    description = _optional_string(raw, "description")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise _PolicyError("'enabled' must be a boolean")

    targets: list[TargetType] = [key for key in KNOWN_TARGET_TYPES if key in raw]
    if len(targets) != 1:
        raise _PolicyError(f"exactly one target of {list(KNOWN_TARGET_TYPES)} must be set, got {targets}")
    target_type = targets[0]

    target: PolicyTarget
    if target_type == TARGET_TYPE_TRACE:
        target = _parse_trace_target(raw[TARGET_TYPE_TRACE])
    else:
        target = _EMPTY_TARGETS[target_type]

    return Policy(
        id=policy_id,
        name=name,
        target=target,
        description=description,
        enabled=enabled,
        created_at_unix_nano=_optional_int(raw, "created_at_unix_nano"),
        modified_at_unix_nano=_optional_int(raw, "modified_at_unix_nano"),
    )


def _parse_trace_target(raw: Any) -> TraceTarget:
    target = _required_object(raw, "trace")
    raw_match = target.get("match")
    if not isinstance(raw_match, list) or not raw_match:
        raise _PolicyError("'trace.match' must be a non-empty array of matchers")
    matchers = tuple(_parse_trace_matcher(raw_matcher) for raw_matcher in cast("list[Any]", raw_match))
    keep = _parse_trace_sampling_config(target.get("keep"))
    return TraceTarget(match=matchers, keep=keep)


def _parse_trace_matcher(raw: Any) -> TraceMatcher:
    matcher = _required_object(raw, "matcher")

    field_keys = [key for key in _FIELD_KEYS if key in matcher]
    if len(field_keys) != 1:
        raise _PolicyError(f"matcher must set exactly one field, got {field_keys}")
    field_key = field_keys[0]
    raw_field_value: Any = matcher[field_key]
    field: TraceMatcherField
    if field_key in _ATTRIBUTE_PATH_FIELD_TYPES:
        field = _ATTRIBUTE_PATH_FIELD_TYPES[field_key](_attribute_path(field_key, raw_field_value))
    elif isinstance(raw_field_value, str):
        field = _STRING_FIELD_TYPES[field_key](raw_field_value)
    else:
        raise _PolicyError(f"matcher field '{field_key}' must be a string")

    match_keys = [key for key in _MATCH_KEYS if key in matcher]
    if len(match_keys) != 1:
        raise _PolicyError(f"matcher must set exactly one match of {list(_MATCH_KEYS)}, got {match_keys}")
    match_key = match_keys[0]
    match_value = matcher[match_key]
    match: MatchPredicate
    if match_key == "exists":
        if not isinstance(match_value, bool):
            raise _PolicyError("matcher 'exists' must be a boolean")
        match = Exists(match_value)
    elif isinstance(match_value, str):
        match = _STRING_MATCH_TYPES[match_key](match_value)
    else:
        raise _PolicyError(f"matcher '{match_key}' must be a string")

    return TraceMatcher(
        field=field,
        match=match,
        negate=_optional_bool(matcher, "negate"),
        case_insensitive=_optional_bool(matcher, "case_insensitive"),
    )


def _attribute_path(field_name: str, raw_value: Any) -> tuple[str, ...]:
    if not isinstance(raw_value, list) or not raw_value:
        raise _PolicyError(f"matcher field '{field_name}' must be a non-empty array of strings")
    segments: list[str] = []
    for segment in cast("list[Any]", raw_value):
        if not isinstance(segment, str):
            raise _PolicyError(f"matcher field '{field_name}' must be a non-empty array of strings")
        segments.append(segment)
    return tuple(segments)


def _parse_trace_sampling_config(raw: Any) -> TraceSamplingConfig:
    keep = _required_object(raw, "trace.keep")
    percentage = _number(keep, "percentage")
    if not 0.0 <= percentage <= 100.0:
        raise _PolicyError(f"'trace.keep.percentage' must be in [0, 100], got {percentage}")
    return TraceSamplingConfig(
        percentage=percentage,
        mode=_optional_string(keep, "mode"),
        sampling_precision=_optional_int(keep, "sampling_precision"),
        hash_seed=_optional_int(keep, "hash_seed"),
        fail_closed=_optional_bool(keep, "fail_closed"),
    )


def _required_object(raw: Any, name: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise _PolicyError(f"'{name}' must be a JSON object")
    return cast("dict[str, Any]", raw)


def _required_string(raw: dict[str, Any], key: str) -> str:
    value: Any = raw.get(key)
    if not isinstance(value, str) or not value:
        raise _PolicyError(f"'{key}' must be a non-empty string")
    return value


def _optional_string(raw: dict[str, Any], key: str) -> str:
    value: Any = raw.get(key, "")
    if not isinstance(value, str):
        raise _PolicyError(f"'{key}' must be a string")
    return value


def _number(raw: dict[str, Any], key: str) -> float:
    # Protobuf JSON allows numbers to be encoded as strings.
    value: Any = raw.get(key)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            raise _PolicyError(f"'{key}' must be a number") from None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _PolicyError(f"'{key}' must be a number")
    return float(value)


def _optional_int(raw: dict[str, Any], key: str) -> int:
    # Protobuf JSON encodes 64-bit integers as strings.
    value: Any = raw.get(key, 0)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            raise _PolicyError(f"'{key}' must be an integer") from None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _PolicyError(f"'{key}' must be an integer")
    return value


def _optional_bool(raw: dict[str, Any], key: str) -> bool:
    value: Any = raw.get(key, False)
    if not isinstance(value, bool):
        raise _PolicyError(f"'{key}' must be a boolean")
    return value
