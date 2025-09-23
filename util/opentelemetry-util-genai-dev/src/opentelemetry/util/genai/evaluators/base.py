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

from abc import ABC, abstractmethod
from typing import List, Union

from opentelemetry.util.genai.types import EvaluationResult, LLMInvocation


class Evaluator(ABC):
    """Abstract evaluator interface.

    Implementations should be lightweight. Heavy/optional dependencies should only be
    imported inside ``evaluate`` to avoid hard runtime requirements for users who do not
    enable that evaluator.
    """

    @abstractmethod
    def evaluate(
        self, invocation: LLMInvocation
    ) -> Union[
        EvaluationResult, List[EvaluationResult]
    ]:  # pragma: no cover - interface
        raise NotImplementedError


__all__ = ["Evaluator"]
