# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal, get_args

# Python structure corresponding to proposed protobuf schema in OTEP 4738.
# Much of the structure is oneofs, which we model directly with union types.

# The policy schema's "target" oneof field names.
TargetType = Literal["log", "metric", "profile", "trace"]
TARGET_TYPE_LOG: Final[TargetType] = "log"
TARGET_TYPE_METRIC: Final[TargetType] = "metric"
TARGET_TYPE_PROFILE: Final[TargetType] = "profile"
TARGET_TYPE_TRACE: Final[TargetType] = "trace"

KNOWN_TARGET_TYPES: tuple[TargetType, ...] = get_args(TargetType)


class SourceKind(Enum):
    """Where a policy came from.

    A lower enum value indicates a higher priority policy and will take precedence
    if multiple are run.
    """

    OPAMP = 1
    HTTP = 2
    FILE = 3
    CUSTOM = 4


# The TraceMatcher's "field" oneof, one type per member.


@dataclass(frozen=True)
class TraceField:
    """A simple trace/span field by name, e.g. ``trace_id``."""

    name: str


@dataclass(frozen=True)
class SpanAttribute:
    path: tuple[str, ...]


@dataclass(frozen=True)
class ResourceAttribute:
    path: tuple[str, ...]


@dataclass(frozen=True)
class ScopeAttribute:
    path: tuple[str, ...]


@dataclass(frozen=True)
class EventAttribute:
    path: tuple[str, ...]


@dataclass(frozen=True)
class SpanKindField:
    value: str


@dataclass(frozen=True)
class SpanStatusField:
    value: str


@dataclass(frozen=True)
class EventNameField:
    value: str


@dataclass(frozen=True)
class LinkTraceIdField:
    value: str


TraceMatcherField = (
    TraceField
    | SpanAttribute
    | ResourceAttribute
    | ScopeAttribute
    | SpanKindField
    | SpanStatusField
    | EventNameField
    | EventAttribute
    | LinkTraceIdField
)


# The matcher's "match" predicate oneof.


@dataclass(frozen=True)
class Exact:
    value: str


@dataclass(frozen=True)
class Regex:
    pattern: str


@dataclass(frozen=True)
class Exists:
    value: bool


@dataclass(frozen=True)
class StartsWith:
    value: str


@dataclass(frozen=True)
class EndsWith:
    value: str


@dataclass(frozen=True)
class Contains:
    value: str


MatchPredicate = Exact | Regex | Exists | StartsWith | EndsWith | Contains


@dataclass(frozen=True)
class TraceMatcher:
    """One matcher from a trace target's ANDed matcher list."""

    field: TraceMatcherField
    match: MatchPredicate
    negate: bool = False
    case_insensitive: bool = False


@dataclass(frozen=True)
class TraceSamplingConfig:
    """The trace target's keep configuration."""

    percentage: float
    mode: str = ""
    sampling_precision: int = 0
    hash_seed: int = 0
    fail_closed: bool = False


@dataclass(frozen=True)
class TraceTarget:
    match: tuple[TraceMatcher, ...]
    keep: TraceSamplingConfig


@dataclass(frozen=True)
class LogTarget:
    """Recognized target with no implementer yet; its content is not modeled."""


@dataclass(frozen=True)
class MetricTarget:
    """Recognized target with no implementer yet; its content is not modeled."""


@dataclass(frozen=True)
class ProfileTarget:
    """Recognized target with no implementer yet; its content is not modeled."""


PolicyTarget = LogTarget | MetricTarget | ProfileTarget | TraceTarget

_TARGET_TYPES_BY_CLASS: dict[type[PolicyTarget], TargetType] = {
    LogTarget: TARGET_TYPE_LOG,
    MetricTarget: TARGET_TYPE_METRIC,
    ProfileTarget: TARGET_TYPE_PROFILE,
    TraceTarget: TARGET_TYPE_TRACE,
}


@dataclass(frozen=True)
class Policy:
    """A parsed telemetry policy."""

    id: str
    name: str
    target: PolicyTarget
    description: str = ""
    enabled: bool = True
    created_at_unix_nano: int = 0
    modified_at_unix_nano: int = 0

    @property
    def target_type(self) -> TargetType:
        return _TARGET_TYPES_BY_CLASS[type(self.target)]


@dataclass(frozen=True)
class PolicyApplyStatus:
    """Outcome of applying one policy, keyed by policy id."""

    policy_id: str
    applied: bool
    error: str = ""
