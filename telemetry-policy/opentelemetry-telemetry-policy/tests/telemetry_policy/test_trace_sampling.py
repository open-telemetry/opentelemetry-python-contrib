# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry._telemetry_policy import (
    Contains,
    EndsWith,
    Exact,
    Exists,
    LogTarget,
    MatchPredicate,
    Policy,
    PolicyStore,
    Regex,
    ResourceAttribute,
    SourceKind,
    SpanAttribute,
    StartsWith,
    TraceField,
    TraceMatcher,
    TraceSamplingConfig,
    TraceSamplingPolicyImplementer,
    TraceTarget,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.util.types import Attributes


def _policy(
    policy_id: str,
    *,
    percentage: float,
    matchers: tuple[TraceMatcher, ...] | None = None,
    enabled: bool = True,
    keep_kwargs: dict[str, Any] | None = None,
) -> Policy:
    if matchers is None:
        matchers = (TraceMatcher(field=SpanAttribute(("db.system",)), match=Exists(True)),)
    return Policy(
        id=policy_id,
        name=policy_id,
        enabled=enabled,
        target=TraceTarget(
            match=matchers,
            keep=TraceSamplingConfig(percentage=percentage, **(keep_kwargs or {})),
        ),
    )


def _span_sampled(implementer: TraceSamplingPolicyImplementer, attributes: Attributes) -> bool:
    tracer_provider = TracerProvider(sampler=implementer.sampler)
    tracer = tracer_provider.get_tracer("test")
    span = tracer.start_span("span", attributes=attributes)
    span.end()
    return span.get_span_context().trace_flags.sampled


def test_no_policies_uses_fallback() -> None:
    implementer = TraceSamplingPolicyImplementer()
    assert _span_sampled(implementer, {"db.system": "postgresql"}) is True


def test_matched_policy_drops_and_unmatched_falls_back() -> None:
    implementer = TraceSamplingPolicyImplementer()
    statuses = implementer.apply_policies([_policy("p1", percentage=0.0)])

    assert [(status.applied, status.error) for status in statuses] == [(True, "")]
    assert _span_sampled(implementer, {"db.system": "postgresql"}) is False
    assert _span_sampled(implementer, {"http.route": "/"}) is True
    assert _span_sampled(implementer, None) is True


def test_matched_policy_at_100_percent_samples() -> None:
    implementer = TraceSamplingPolicyImplementer()
    implementer.apply_policies([_policy("p1", percentage=100.0)])

    assert _span_sampled(implementer, {"db.system": "postgresql"}) is True


def test_most_restrictive_policy_wins() -> None:
    implementer = TraceSamplingPolicyImplementer()
    implementer.apply_policies(
        [
            _policy("keep-all", percentage=100.0),
            _policy("drop-all", percentage=0.0),
        ]
    )

    assert _span_sampled(implementer, {"db.system": "postgresql"}) is False


def test_policy_change_applies_to_existing_tracer() -> None:
    implementer = TraceSamplingPolicyImplementer()
    tracer_provider = TracerProvider(sampler=implementer.sampler)
    tracer = tracer_provider.get_tracer("test")
    attributes = {"db.system": "postgresql"}

    span = tracer.start_span("span", attributes=attributes)
    span.end()
    assert span.get_span_context().trace_flags.sampled is True

    implementer.apply_policies([_policy("p1", percentage=0.0)])
    span = tracer.start_span("span", attributes=attributes)
    span.end()
    assert span.get_span_context().trace_flags.sampled is False

    implementer.apply_policies([])
    span = tracer.start_span("span", attributes=attributes)
    span.end()
    assert span.get_span_context().trace_flags.sampled is True


def test_child_span_follows_parent_decision() -> None:
    implementer = TraceSamplingPolicyImplementer()
    implementer.apply_policies([_policy("p1", percentage=0.0)])
    tracer_provider = TracerProvider(sampler=implementer.sampler)
    tracer = tracer_provider.get_tracer("test")

    root = tracer.start_span("root", attributes={"db.system": "postgresql"})
    with trace.use_span(root, end_on_exit=True):
        child = tracer.start_span("child", attributes={"http.route": "/"})
        child.end()

    assert root.get_span_context().trace_flags.sampled is False
    assert child.get_span_context().trace_flags.sampled is False


def test_matcher_kinds() -> None:
    def matcher(match: MatchPredicate, **kwargs: Any) -> tuple[TraceMatcher, ...]:
        return (TraceMatcher(field=SpanAttribute(("http.route",)), match=match, **kwargs),)

    cases = [
        # (matchers, matching attributes, non-matching attributes)
        (matcher(Exact("/health")), {"http.route": "/health"}, {"http.route": "/Health"}),
        (matcher(Exact("/health"), case_insensitive=True), {"http.route": "/HEALTH"}, {"http.route": "/x"}),
        (matcher(StartsWith("/health")), {"http.route": "/health/live"}, {"http.route": "/api/health"}),
        (matcher(EndsWith("live")), {"http.route": "/health/live"}, {"http.route": "/live/x"}),
        (matcher(Contains("health")), {"http.route": "/api/health/x"}, {"http.route": "/api"}),
        (matcher(Regex("^/health(/.*)?$")), {"http.route": "/health/live"}, {"http.route": "/api/health"}),
        (matcher(Exists(False)), {"other": "x"}, {"http.route": "/x"}),
        (matcher(Exact("/health"), negate=True), {"http.route": "/x"}, {"http.route": "/health"}),
        # Non-string attribute values are matched by their string form.
        (
            (TraceMatcher(field=SpanAttribute(("retry.count",)), match=Exact("3")),),
            {"retry.count": 3},
            {"retry.count": 4},
        ),
    ]
    for matchers, matching, non_matching in cases:
        implementer = TraceSamplingPolicyImplementer()
        statuses = implementer.apply_policies([_policy("p1", percentage=0.0, matchers=matchers)])
        assert statuses[0].applied is True
        assert _span_sampled(implementer, matching) is False, matchers
        assert _span_sampled(implementer, non_matching) is True, matchers


def test_global_trace_id_matcher() -> None:
    # The schema's idiom for a policy applying to all traces.
    global_matcher = (TraceMatcher(field=TraceField("trace_id"), match=Exists(True)),)
    implementer = TraceSamplingPolicyImplementer()

    statuses = implementer.apply_policies([_policy("global", percentage=0.0, matchers=global_matcher)])

    assert statuses[0].applied is True
    assert _span_sampled(implementer, {"db.system": "postgresql"}) is False
    assert _span_sampled(implementer, None) is False


def test_ignored_keep_fields_still_apply_rate() -> None:
    implementer = TraceSamplingPolicyImplementer()

    statuses = implementer.apply_policies(
        [
            _policy(
                "p1",
                percentage=0.0,
                keep_kwargs={"mode": "equalizing", "sampling_precision": 6, "fail_closed": True},
            )
        ]
    )

    assert statuses[0].applied is True
    assert _span_sampled(implementer, {"db.system": "postgresql"}) is False


def test_unsupported_policies_fail_open() -> None:
    unsupported = [
        _policy(
            "trace-field",
            percentage=5.0,
            matchers=(TraceMatcher(field=TraceField("span_name"), match=Exists(True)),),
        ),
        _policy("hash-seed", percentage=5.0, keep_kwargs={"hash_seed": 7}),
        _policy(
            "nested-path",
            percentage=5.0,
            matchers=(TraceMatcher(field=SpanAttribute(("a", "b")), match=Exists(True)),),
        ),
        _policy(
            "resource-attribute",
            percentage=5.0,
            matchers=(TraceMatcher(field=ResourceAttribute(("service.name",)), match=Exists(True)),),
        ),
        _policy(
            "bad-regex",
            percentage=5.0,
            matchers=(TraceMatcher(field=SpanAttribute(("http.route",)), match=Regex("[unclosed")),),
        ),
    ]
    implementer = TraceSamplingPolicyImplementer()

    statuses = implementer.apply_policies([*unsupported, _policy("drop-all", percentage=0.0)])

    for status in statuses[:-1]:
        assert status.applied is False, status
        assert status.error, status
    assert statuses[-1].applied is True
    assert _span_sampled(implementer, {"db.system": "postgresql"}) is False


def test_disabled_policy_not_evaluated_but_applied() -> None:
    implementer = TraceSamplingPolicyImplementer()

    statuses = implementer.apply_policies([_policy("p1", percentage=0.0, enabled=False)])

    assert statuses[0].applied is True
    assert _span_sampled(implementer, {"db.system": "postgresql"}) is True


def test_policy_without_trace_target_reports_error() -> None:
    implementer = TraceSamplingPolicyImplementer()

    statuses = implementer.apply_policies([Policy(id="p1", name="p1", target=LogTarget())])

    assert statuses[0].applied is False
    assert "no trace target" in statuses[0].error


def test_works_through_policy_store() -> None:
    implementer = TraceSamplingPolicyImplementer()
    store = PolicyStore()
    store.add_implementer(implementer)

    statuses = store.set_policies(SourceKind.FILE, [_policy("p1", percentage=0.0)])

    assert statuses[0].applied is True
    assert _span_sampled(implementer, {"db.system": "postgresql"}) is False
