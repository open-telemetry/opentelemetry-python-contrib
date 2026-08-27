# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from opentelemetry._telemetry_policy.model import Policy, PolicyApplyStatus, TargetType


class PolicyImplementer(ABC):
    """Applies policies of one target type to the running SDK."""

    @property
    @abstractmethod
    def target_type(self) -> TargetType:
        """The policy target type this implementer handles, e.g. ``trace``."""

    @abstractmethod
    def apply_policies(self, policies: Sequence[Policy]) -> Sequence[PolicyApplyStatus]:
        """Apply the effective policy set, returning one status per policy."""
