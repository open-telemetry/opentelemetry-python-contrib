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

"""Metric instrument definitions for OpenAI Agents GenAI instrumentation.

We expose a minimal stable set of metrics (development status):
  - gen_ai.client.operation.duration (Histogram, seconds)
  - gen_ai.client.tokens.input (Counter, tokens)
  - gen_ai.client.tokens.output (Counter, tokens)
  - gen_ai.client.requests (Counter, requests)

Helper functions create instruments lazily (idempotent) to avoid side-effects
when metrics are disabled via environment flag.
"""

from __future__ import annotations

from typing import Dict

from opentelemetry import metrics

METER_NAME = "opentelemetry.instrumentation.openai_agents"

_METER = None
_INSTRUMENTS: Dict[str, object] = {}


def _get_meter():
    global _METER
    if _METER is None:
        _METER = metrics.get_meter(METER_NAME)
    return _METER


def get_instruments() -> Dict[str, object]:
    """Create (if needed) and return metric instruments."""
    meter = _get_meter()
    if "duration" not in _INSTRUMENTS:
        _INSTRUMENTS["duration"] = meter.create_histogram(
            name="gen_ai.client.operation.duration",
            unit="s",
            description="Duration of GenAI client operations",
        )
    if "requests" not in _INSTRUMENTS:
        _INSTRUMENTS["requests"] = meter.create_counter(
            name="gen_ai.client.requests",
            unit="1",
            description="Number of GenAI client operations",
        )
    if "tokens_input" not in _INSTRUMENTS:
        _INSTRUMENTS["tokens_input"] = meter.create_counter(
            name="gen_ai.client.tokens.input",
            unit="token",
            description="Input (prompt) tokens consumed",
        )
    if "tokens_output" not in _INSTRUMENTS:
        _INSTRUMENTS["tokens_output"] = meter.create_counter(
            name="gen_ai.client.tokens.output",
            unit="token",
            description="Output (completion) tokens produced",
        )
    return _INSTRUMENTS


def record_duration(seconds: float, **attrs) -> None:
    inst = get_instruments()["duration"]
    inst.record(seconds, attributes=attrs)  # type: ignore[attr-defined]


def record_request(**attrs) -> None:
    get_instruments()["requests"].add(1, attributes=attrs)  # type: ignore[attr-defined]


def record_tokens(
    input_tokens: int | None, output_tokens: int | None, **attrs
) -> None:
    if input_tokens is not None:
        get_instruments()["tokens_input"].add(input_tokens, attributes=attrs)  # type: ignore[attr-defined]
    if output_tokens is not None:
        get_instruments()["tokens_output"].add(output_tokens, attributes=attrs)  # type: ignore[attr-defined]
