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
from opentelemetry.sdk.extension.aws.trace.sampler._rate_limiter import (
    _RateLimiter,
)
from opentelemetry.sdk.trace.sampling import Decision, Sampler, SamplingResult
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes


class _RateLimitingSampler(Sampler):
    def __init__(self, quota: int, clock: _Clock):
        self.__quota = quota
        self.__reservoir = _RateLimiter(1, quota, clock)

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
        if self.__reservoir.try_spend(1):
            return SamplingResult(
                decision=Decision.RECORD_AND_SAMPLE,
                attributes=attributes,
                trace_state=trace_state,
            )
        return SamplingResult(
            decision=Decision.DROP,
            attributes=attributes,
            trace_state=trace_state,
        )

    def get_description(self) -> str:
        description = f"RateLimitingSampler{{rate limiting sampling with sampling config of {self.__quota} req/sec and 0% of additional requests}}"
        return description
