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

from typing import Callable, Dict, List

from opentelemetry.util.genai.evaluators.base import Evaluator

_EVALUATORS: Dict[str, Callable[[], Evaluator]] = {}


def register_evaluator(name: str, factory: Callable[[], Evaluator]) -> None:
    """Register an evaluator factory under a given name (case-insensitive).

    Subsequent registrations with the same (case-insensitive) name override the prior one.
    """
    _EVALUATORS[name.lower()] = factory


def get_evaluator(name: str) -> Evaluator:
    key = name.lower()
    factory = _EVALUATORS.get(key)
    if factory is None:
        raise ValueError(f"Unknown evaluator: {name}")
    return factory()


def list_evaluators() -> List[str]:
    return sorted(_EVALUATORS.keys())


__all__ = ["register_evaluator", "get_evaluator", "list_evaluators"]
