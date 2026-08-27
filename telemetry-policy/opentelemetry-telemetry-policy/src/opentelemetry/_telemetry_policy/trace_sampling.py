# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from logging import getLogger
from typing import Sequence

from opentelemetry._telemetry_policy.implementer import PolicyImplementer
from opentelemetry._telemetry_policy.model import (
    TARGET_TYPE_TRACE,
    EndsWith,
    Exact,
    Exists,
    Policy,
    PolicyApplyStatus,
    Regex,
    SpanAttribute,
    StartsWith,
    TargetType,
    TraceField,
    TraceMatcher,
    TraceTarget,
)
from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_ON,
    ParentBased,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.trace import Link, SpanKind, format_trace_id
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

_logger = getLogger(__name__)


class _UnsupportedPolicyError(Exception):
    pass


class _CompiledMatcher:
    """A matcher compiled for evaluation at sampling time."""

    def __init__(self, matcher: TraceMatcher) -> None:
        field = matcher.field
        self._key = ""
        self._is_trace_id = False
        if isinstance(field, TraceField):
            if field.name != "trace_id":
                raise _UnsupportedPolicyError(f"trace_field {field.name!r} is not supported, only 'trace_id'")
            self._is_trace_id = True
        elif isinstance(field, SpanAttribute):
            if len(field.path) != 1:
                raise _UnsupportedPolicyError(
                    "nested span_attribute paths are not supported, use a single attribute key"
                )
            self._key = field.path[0]
        else:
            raise _UnsupportedPolicyError(
                f"matcher field {type(field).__name__} is not supported, only span_attribute and trace_field"
            )
        self._predicate = matcher.match
        self._negate = matcher.negate
        self._case_insensitive = matcher.case_insensitive
        self._pattern: re.Pattern[str] | None = None
        self._text = ""
        if isinstance(self._predicate, Regex):
            flags = re.IGNORECASE if matcher.case_insensitive else 0
            try:
                self._pattern = re.compile(self._predicate.pattern, flags)
            except re.error as exc:
                raise _UnsupportedPolicyError(f"invalid regex '{self._predicate.pattern}': {exc}") from exc
        elif not isinstance(self._predicate, Exists):
            self._text = self._predicate.value.lower() if matcher.case_insensitive else self._predicate.value

    def matches(self, trace_id_hex: str, attributes: Attributes) -> bool:
        if self._is_trace_id:
            value = trace_id_hex
        else:
            value = attributes.get(self._key) if attributes else None
        predicate = self._predicate
        if isinstance(predicate, Exists):
            result = (value is not None) == predicate.value
        elif value is None:
            result = False
        else:
            text = value if isinstance(value, str) else str(value)
            if self._pattern is not None:
                result = self._pattern.search(text) is not None
            else:
                if self._case_insensitive:
                    text = text.lower()
                if isinstance(predicate, Exact):
                    result = text == self._text
                elif isinstance(predicate, StartsWith):
                    result = text.startswith(self._text)
                elif isinstance(predicate, EndsWith):
                    result = text.endswith(self._text)
                else:  # Contains
                    result = self._text in text
        return not result if self._negate else result


class _CompiledTracePolicy:
    def __init__(self, policy_id: str, trace: TraceTarget) -> None:
        keep = trace.keep
        if keep.hash_seed != 0:
            # TODO: Need spec clarification on how to hash when seed is present.
            raise _UnsupportedPolicyError("a non-zero hash_seed is not supported")
        self.policy_id = policy_id
        self.percentage = keep.percentage
        self.sampler = TraceIdRatioBased(keep.percentage / 100.0)
        self._matchers = tuple(_CompiledMatcher(matcher) for matcher in trace.match)

    def matches(self, trace_id_hex: str, attributes: Attributes) -> bool:
        return all(matcher.matches(trace_id_hex, attributes) for matcher in self._matchers)


class _PolicyRootSampler(Sampler):
    """Root sampler evaluating the current trace policy snapshot per span."""

    def __init__(self, fallback: Sampler) -> None:
        self._fallback = fallback
        self._policies: tuple[_CompiledTracePolicy, ...] = ()

    def set_policies(self, policies: Sequence[_CompiledTracePolicy]) -> None:
        self._policies = tuple(policies)

    def set_fallback(self, fallback: Sampler) -> None:
        self._fallback = fallback

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        policies = self._policies
        chosen: _CompiledTracePolicy | None = None
        if policies:
            trace_id_hex = format_trace_id(trace_id)
            for policy in policies:
                if (chosen is None or policy.percentage < chosen.percentage) and policy.matches(
                    trace_id_hex, attributes
                ):
                    chosen = policy
        sampler = chosen.sampler if chosen is not None else self._fallback
        return sampler.should_sample(parent_context, trace_id, name, kind, attributes, links, trace_state)

    def get_description(self) -> str:
        return f"TelemetryPolicyRootSampler{{fallback={self._fallback.get_description()}}}"


class TraceSamplingPolicyImplementer(PolicyImplementer):
    """Applies trace sampling policies through a runtime-swappable sampler.

    Args:
        fallback: root sampler used for spans no policy matches. Defaults to always-on.
    """

    def __init__(self, fallback: Sampler | None = None) -> None:
        self._root = _PolicyRootSampler(fallback or ALWAYS_ON)
        self._sampler = ParentBased(root=self._root)

    @property
    def sampler(self) -> Sampler:
        return self._sampler

    def set_fallback(self, fallback: Sampler) -> None:
        """Set the root sampler used for spans no policy matches."""
        self._root.set_fallback(fallback)

    @property
    def target_type(self) -> TargetType:
        return TARGET_TYPE_TRACE

    def apply_policies(self, policies: Sequence[Policy]) -> Sequence[PolicyApplyStatus]:
        statuses: list[PolicyApplyStatus] = []
        compiled: list[_CompiledTracePolicy] = []
        for policy in policies:
            if not isinstance(policy.target, TraceTarget):
                statuses.append(
                    PolicyApplyStatus(policy_id=policy.id, applied=False, error="policy has no trace target")
                )
                continue
            # Disabled policies must not be evaluated but count as applied.
            if not policy.enabled:
                statuses.append(PolicyApplyStatus(policy_id=policy.id, applied=True))
                continue
            try:
                compiled.append(_CompiledTracePolicy(policy.id, policy.target))
            except _UnsupportedPolicyError as exc:
                _logger.warning("skipping trace sampling policy '%s': %s", policy.id, exc)
                statuses.append(PolicyApplyStatus(policy_id=policy.id, applied=False, error=str(exc)))
                continue
            statuses.append(PolicyApplyStatus(policy_id=policy.id, applied=True))
        self._root.set_policies(compiled)
        return statuses
