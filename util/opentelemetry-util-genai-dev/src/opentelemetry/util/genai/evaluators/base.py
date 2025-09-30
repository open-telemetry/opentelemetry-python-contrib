# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import deque
from threading import Lock
from typing import List, Union

from opentelemetry.util.genai.types import EvaluationResult, LLMInvocation


class Evaluator(ABC):
    """Abstract evaluator interface (asynchronous model).

    New contract (async sampling model):
      * ``offer(invocation) -> bool`` performs lightweight sampling & queueing (implemented by manager)
      * ``evaluate_invocation(invocation)`` performs the heavy evaluation logic for a *single* invocation, returning
        an EvaluationResult or list thereof. It is called off the hot path by the background evaluation runner.

    Implementations MUST keep ``evaluate_invocation`` idempotent and side‑effect free on the input invocation object.
    Heavy / optional dependencies should be imported lazily inside ``evaluate_invocation``.
    """

    def __init__(self):  # pragma: no cover - simple init
        self._queue = deque()  # type: ignore[var-annotated]
        self._lock = Lock()
        self._sample_timestamps: list[float] = []  # per-minute rate limiting

    def should_sample(
        self, invocation: LLMInvocation
    ) -> bool:  # pragma: no cover - trivial default
        return True

    def evaluate(
        self,
        invocation: LLMInvocation,
        max_per_minute: int = 0,
    ) -> bool:
        """Lightweight sampling + enqueue.

        Returns True if the invocation was enqueued for asynchronous evaluation.
        Applies optional per-minute rate limiting (shared per evaluator instance).
        """
        if not self.should_sample(invocation):
            return False
        now = time.time()
        if max_per_minute > 0:
            # prune old timestamps
            cutoff = now - 60
            with self._lock:
                self._sample_timestamps = [
                    t for t in self._sample_timestamps if t >= cutoff
                ]
                if len(self._sample_timestamps) >= max_per_minute:
                    return False
                self._sample_timestamps.append(now)
                self._queue.append(invocation)
            return True
        else:
            with self._lock:
                self._queue.append(invocation)
            return True

    def _drain_queue(
        self, max_items: int | None = None
    ) -> list[LLMInvocation]:  # pragma: no cover - exercised indirectly
        items: list[LLMInvocation] = []
        with self._lock:
            if max_items is None:
                while self._queue:
                    items.append(self._queue.popleft())
            else:
                while self._queue and len(items) < max_items:
                    items.append(self._queue.popleft())
        return items

    @abstractmethod
    def evaluate_invocation(
        self, invocation: LLMInvocation
    ) -> Union[
        EvaluationResult, List[EvaluationResult]
    ]:  # pragma: no cover - interface
        raise NotImplementedError


__all__ = ["Evaluator"]
