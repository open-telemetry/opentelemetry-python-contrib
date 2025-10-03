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

from typing import List, Union

from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import EvaluationResult, LLMInvocation


class DeepevalEvaluator(Evaluator):
    """Deepeval evaluator"""

    def __init__(self, handler):  # pragma: no cover - simple init
        # self._queue = deque()  # type: ignore[var-annotated]
        self._sample_timestamps: list[float] = []  # per-minute rate limiting
        self._handler: TelemetryHandler = handler

    def should_sample(
        self, invocation: LLMInvocation
    ) -> bool:  # pragma: no cover - trivial default
        return True

    def evaluate(
        self,
        invocation: LLMInvocation,
        max_per_minute: int = 0,
    ) -> bool:
        # TODO: deepeval specific evaluation logic
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

    def evaluate_invocation(
        self, invocation: LLMInvocation
    ) -> Union[
        EvaluationResult, List[EvaluationResult]
    ]:  # pragma: no cover - interface
        # self._handler.evaluation_result(new EvaluationResult("fake result"))
        raise NotImplementedError


__all__ = ["Evaluator"]
