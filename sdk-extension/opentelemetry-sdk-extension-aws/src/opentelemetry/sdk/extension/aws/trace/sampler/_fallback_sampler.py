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

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Sequence

# pylint: disable=no-name-in-module
from opentelemetry.context import Context
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock
from opentelemetry.sdk.extension.aws.trace.sampler._rate_limiting_sampler import (
    _RateLimitingSampler,
)
from opentelemetry.sdk.trace.sampling import (
    Decision,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes


class _FallbackSampler(Sampler):  # pyright: ignore[reportUnusedClass]
    def __init__(self, clock: _Clock):
        self.__rate_limiting_sampler = _RateLimitingSampler(1, clock)
        self.__fixed_rate_sampler = TraceIdRatioBased(0.05)

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes | None = None,
        links: Sequence["Link"] | None = None,
        trace_state: TraceState | None = None,
    ) -> "SamplingResult":
        sampling_result = self.__rate_limiting_sampler.should_sample(
            parent_context,
            trace_id,
            name,
            kind=kind,
            attributes=attributes,
            links=links,
            trace_state=trace_state,
        )
        if sampling_result.decision is not Decision.DROP:
            return sampling_result
        return self.__fixed_rate_sampler.should_sample(
            parent_context,
            trace_id,
            name,
            kind=kind,
            attributes=attributes,
            links=links,
            trace_state=trace_state,
        )

    # pylint: disable=no-self-use
    def get_description(self) -> str:
        description = "FallbackSampler{fallback sampling with sampling config of 1 req/sec and 5% of additional requests}"
        return description
