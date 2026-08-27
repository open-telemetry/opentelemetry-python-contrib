# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading
from logging import getLogger
from typing import Sequence

from opentelemetry._telemetry_policy.implementer import PolicyImplementer
from opentelemetry._telemetry_policy.model import (
    Policy,
    PolicyApplyStatus,
    SourceKind,
    TargetType,
)

_logger = getLogger(__name__)


class PolicyStore:
    """Aggregates policy snapshots from providers and applies them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshots: dict[SourceKind, tuple[Policy, ...]] = {}
        self._implementers: dict[TargetType, PolicyImplementer] = {}

    def add_implementer(self, implementer: PolicyImplementer) -> None:
        """Register the implementer for its target type and apply the current effective policies to it."""
        with self._lock:
            target_type = implementer.target_type
            if target_type in self._implementers:
                raise ValueError(f"an implementer for target type '{target_type}' is already registered")
            self._implementers[target_type] = implementer
            effective = self._effective_policies()
            self._apply(
                implementer,
                [policy for policy in effective if policy.target_type == target_type],
            )

    def set_policies(self, source: SourceKind, policies: Sequence[Policy]) -> tuple[PolicyApplyStatus, ...]:
        """Replace ``source``'s policy snapshot and re-apply the effective set."""
        with self._lock:
            self._snapshots[source] = tuple(policies)
            effective = self._effective_policies()
            effective_by_key = {(policy.target_type, policy.id): policy for policy in effective}

            statuses_by_key: dict[tuple[TargetType, str], PolicyApplyStatus] = {}
            for target_type, implementer in self._implementers.items():
                subset = [policy for policy in effective if policy.target_type == target_type]
                for status in self._apply(implementer, subset):
                    statuses_by_key[(target_type, status.policy_id)] = status

            statuses: list[PolicyApplyStatus] = []
            seen_keys: set[tuple[TargetType, str]] = set()
            for policy in policies:
                key = (policy.target_type, policy.id)
                if not policy.enabled:
                    # A disabled policy is treated as if it does not exist and is a success.
                    statuses.append(PolicyApplyStatus(policy_id=policy.id, applied=True))
                elif effective_by_key.get(key) != policy:
                    if key in seen_keys:
                        error = "a different policy earlier in this snapshot with the same id took precedence"
                    else:
                        error = "overridden by a different policy with the same id from a higher-priority source"
                    statuses.append(PolicyApplyStatus(policy_id=policy.id, applied=False, error=error))
                elif key in statuses_by_key:
                    statuses.append(statuses_by_key[key])
                else:
                    statuses.append(
                        PolicyApplyStatus(
                            policy_id=policy.id,
                            applied=False,
                            error=f"no implementer registered for target type '{policy.target_type}'",
                        )
                    )
                seen_keys.add(key)
            return tuple(statuses)

    def _effective_policies(self) -> list[Policy]:
        merged: dict[tuple[TargetType, str], Policy] = {}
        for source in sorted(self._snapshots, key=lambda kind: kind.value):
            for policy in self._snapshots[source]:
                if not policy.enabled:
                    continue
                key = (policy.target_type, policy.id)
                if key in merged:
                    continue
                merged[key] = policy
        return sorted(merged.values(), key=lambda policy: (policy.target_type, policy.id))

    @staticmethod
    def _apply(implementer: PolicyImplementer, policies: Sequence[Policy]) -> Sequence[PolicyApplyStatus]:
        try:
            return implementer.apply_policies(policies)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _logger.exception("policy implementer for '%s' failed", implementer.target_type)
            return [
                PolicyApplyStatus(policy_id=policy.id, applied=False, error=f"implementer failed: {exc}")
                for policy in policies
            ]
