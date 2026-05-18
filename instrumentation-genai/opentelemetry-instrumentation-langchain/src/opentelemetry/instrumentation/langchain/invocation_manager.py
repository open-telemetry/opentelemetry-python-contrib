# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import UUID

from opentelemetry.util.genai.types import GenAIInvocation

__all__ = ["_InvocationManager"]


@dataclass
class _InvocationState:
    invocation: GenAIInvocation
    children: List[UUID] = field(default_factory=lambda: list())


class _InvocationManager:
    def __init__(
        self,
    ) -> None:
        # Map from run_id -> _InvocationState, to keep track of invocations and parent/child relationships
        # TODO: TTL cache to avoid memory leaks in long-running processes.
        self._invocations: Dict[UUID, _InvocationState] = {}

    def add_invocation_state(
        self,
        run_id: UUID,
        parent_run_id: Optional[UUID],
        invocation: GenAIInvocation,
    ):
        invocation_state = _InvocationState(invocation=invocation)
        self._invocations[run_id] = invocation_state

        if parent_run_id is not None and parent_run_id in self._invocations:
            parent_invocation_state = self._invocations[parent_run_id]
            parent_invocation_state.children.append(run_id)

    def get_invocation(self, run_id: UUID) -> Optional[GenAIInvocation]:
        invocation_state = self._invocations.get(run_id)
        return invocation_state.invocation if invocation_state else None

    def delete_invocation_state(self, run_id: UUID) -> None:
        invocation_state = self._invocations.get(run_id)
        if not invocation_state:
            return
        for child_id in list(invocation_state.children):
            self._invocations.pop(child_id, None)
        self._invocations.pop(run_id, None)
