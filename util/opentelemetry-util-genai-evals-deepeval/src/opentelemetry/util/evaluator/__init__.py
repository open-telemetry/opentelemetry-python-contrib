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

"""Evaluator scaffolding (Phase 1).

Provides a minimal pluggable registry for GenAI evaluators. Future phases will
add concrete implementations (e.g., deepeval) and telemetry emission.
"""

from opentelemetry.util.genai.evaluators import (
    builtins as _builtins,  # noqa: E402,F401  (auto-registration side effects)
)
from opentelemetry.util.genai.evaluators.base import Evaluator
from opentelemetry.util.genai.evaluators.registry import get_evaluator, list_evaluators, register_evaluator

__all__ = [
    "Evaluator",
    "register_evaluator",
    "get_evaluator",
    "list_evaluators",
]
