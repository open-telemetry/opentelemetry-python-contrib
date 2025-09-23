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
"""Lightweight span-only telemetry generator for GenAI invocations.

This implementation now delegates common span lifecycle & attribute logic
entirely to BaseSpanGenerator to avoid duplication.
"""

from __future__ import annotations

from typing import Optional

from opentelemetry.trace import Tracer

from .base_span_generator import BaseSpanGenerator


class SpanGenerator(BaseSpanGenerator):
    """Spans only.

    Capture of input/output message content as span attributes is controlled
    by the boolean ``capture_content`` passed to the constructor (interpreted
    by ``BaseSpanGenerator``). No metrics or events are produced.
    """

    def __init__(
        self, tracer: Optional[Tracer] = None, capture_content: bool = False
    ):  # noqa: D401
        super().__init__(tracer=tracer, capture_content=capture_content)
