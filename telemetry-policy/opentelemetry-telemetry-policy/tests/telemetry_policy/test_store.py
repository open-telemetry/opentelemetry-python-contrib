# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Sequence

import pytest

from opentelemetry._telemetry_policy import (
    Exists,
    LogTarget,
    Policy,
    PolicyApplyStatus,
    PolicyImplementer,
    PolicyStore,
    SourceKind,
    SpanAttribute,
    TargetType,
    TraceMatcher,
    TraceSamplingConfig,
    TraceTarget,
)


def _trace_policy(policy_id: str, percentage: float = 5.0, enabled: bool = True) -> Policy:
    return Policy(
        id=policy_id,
        name=policy_id,
        enabled=enabled,
        target=TraceTarget(
            match=(TraceMatcher(field=SpanAttribute(("db.system",)), match=Exists(True)),),
            keep=TraceSamplingConfig(percentage=percentage),
        ),
    )


def _log_policy(policy_id: str, enabled: bool = True) -> Policy:
    return Policy(id=policy_id, name=policy_id, target=LogTarget(), enabled=enabled)


class _RecordingImplementer(PolicyImplementer):
    def __init__(self, target_type: TargetType = "trace") -> None:
        self._target_type = target_type
        self.calls: list[tuple[Policy, ...]] = []

    @property
    def target_type(self) -> TargetType:
        return self._target_type

    def apply_policies(self, policies: Sequence[Policy]) -> Sequence[PolicyApplyStatus]:
        self.calls.append(tuple(policies))
        return [PolicyApplyStatus(policy_id=policy.id, applied=True) for policy in policies]


class _CrashingImplementer(PolicyImplementer):
    @property
    def target_type(self) -> TargetType:
        return "trace"

    def apply_policies(self, policies: Sequence[Policy]) -> Sequence[PolicyApplyStatus]:
        raise RuntimeError("boom")


def test_policies_applied_and_acknowledged() -> None:
    store = PolicyStore()
    implementer = _RecordingImplementer()
    store.add_implementer(implementer)
    policy = _trace_policy("p1")

    statuses = store.set_policies(SourceKind.FILE, [policy])

    assert statuses == (PolicyApplyStatus(policy_id="p1", applied=True),)
    assert implementer.calls[-1] == (policy,)


def test_add_implementer_applies_current_policies() -> None:
    store = PolicyStore()
    policy = _trace_policy("p1")
    store.set_policies(SourceKind.FILE, [policy])

    implementer = _RecordingImplementer()
    store.add_implementer(implementer)

    assert implementer.calls == [(policy,)]


def test_duplicate_implementer_target_rejected() -> None:
    store = PolicyStore()
    store.add_implementer(_RecordingImplementer())
    with pytest.raises(ValueError):
        store.add_implementer(_RecordingImplementer())


def test_full_snapshot_replacement_removes_old_policies() -> None:
    store = PolicyStore()
    implementer = _RecordingImplementer()
    store.add_implementer(implementer)
    store.set_policies(SourceKind.FILE, [_trace_policy("p1"), _trace_policy("p2")])

    new_policy = _trace_policy("p3")
    store.set_policies(SourceKind.FILE, [new_policy])

    assert implementer.calls[-1] == (new_policy,)

    store.set_policies(SourceKind.FILE, [])
    assert implementer.calls[-1] == ()


def test_higher_priority_source_wins_duplicate_policy_id() -> None:
    store = PolicyStore()
    implementer = _RecordingImplementer()
    store.add_implementer(implementer)
    file_policy = _trace_policy("p1", percentage=50.0)
    opamp_policy = _trace_policy("p1", percentage=5.0)

    file_statuses = store.set_policies(SourceKind.FILE, [file_policy])
    assert file_statuses[0].applied is True

    opamp_statuses = store.set_policies(SourceKind.OPAMP, [opamp_policy])
    assert opamp_statuses[0].applied is True
    assert implementer.calls[-1] == (opamp_policy,)

    # Re-sending the file snapshot reports the loss to the file source and
    # keeps the OpAMP policy in effect.
    file_statuses = store.set_policies(SourceKind.FILE, [file_policy])
    assert file_statuses[0].applied is False
    assert "higher-priority" in file_statuses[0].error
    assert implementer.calls[-1] == (opamp_policy,)


def test_disabled_policy_does_not_exist_for_merging() -> None:
    store = PolicyStore()
    implementer = _RecordingImplementer()
    store.add_implementer(implementer)
    disabled_opamp = _trace_policy("p1", percentage=0.0, enabled=False)
    enabled_file = _trace_policy("p1", percentage=0.0)

    opamp_statuses = store.set_policies(SourceKind.OPAMP, [disabled_opamp])
    file_statuses = store.set_policies(SourceKind.FILE, [enabled_file])

    assert opamp_statuses == (PolicyApplyStatus(policy_id="p1", applied=True),)
    assert file_statuses == (PolicyApplyStatus(policy_id="p1", applied=True),)
    assert implementer.calls[-1] == (enabled_file,)


def test_disabled_policy_without_implementer_counts_as_applied() -> None:
    store = PolicyStore()

    statuses = store.set_policies(SourceKind.FILE, [_log_policy("p1", enabled=False)])

    assert statuses == (PolicyApplyStatus(policy_id="p1", applied=True),)


def test_duplicate_id_within_snapshot_first_wins() -> None:
    store = PolicyStore()
    implementer = _RecordingImplementer()
    store.add_implementer(implementer)
    first = _trace_policy("p1", percentage=0.0)
    second = _trace_policy("p1", percentage=100.0)

    statuses = store.set_policies(SourceKind.FILE, [first, second])

    assert statuses[0].applied is True
    assert statuses[1].applied is False
    assert "earlier in this snapshot" in statuses[1].error
    assert implementer.calls[-1] == (first,)


def test_identical_duplicate_from_lower_priority_source_is_applied() -> None:
    store = PolicyStore()
    store.add_implementer(_RecordingImplementer())
    policy = _trace_policy("p1")
    store.set_policies(SourceKind.OPAMP, [policy])

    statuses = store.set_policies(SourceKind.FILE, [policy])

    assert statuses[0].applied is True


def test_no_implementer_reports_not_applied() -> None:
    store = PolicyStore()
    store.add_implementer(_RecordingImplementer(target_type="trace"))

    statuses = store.set_policies(SourceKind.FILE, [_log_policy("p1"), _trace_policy("p2")])

    assert statuses[0].applied is False
    assert "no implementer" in statuses[0].error
    assert statuses[1].applied is True


def test_crashing_implementer_fails_open() -> None:
    store = PolicyStore()
    store.add_implementer(_CrashingImplementer())

    statuses = store.set_policies(SourceKind.FILE, [_trace_policy("p1")])

    assert statuses[0].applied is False
    assert "implementer failed" in statuses[0].error
