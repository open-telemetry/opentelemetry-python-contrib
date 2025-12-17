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

from logging import getLogger
from threading import Lock
from typing import Dict, List, Sequence

# pylint: disable=no-name-in-module
from opentelemetry.context import Context
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock
from opentelemetry.sdk.extension.aws.trace.sampler._fallback_sampler import (
    _FallbackSampler,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_rule import (
    _SamplingRule,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_rule_applier import (
    _SamplingRuleApplier,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_target import (
    _SamplingTarget,
    _SamplingTargetResponse,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import SamplingResult
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

_logger = getLogger(__name__)

CACHE_TTL_SECONDS = 3600
DEFAULT_TARGET_POLLING_INTERVAL_SECONDS = 10


class _RuleCache:  # pyright: ignore[reportUnusedClass]
    def __init__(
        self,
        resource: Resource,
        fallback_sampler: _FallbackSampler,
        client_id: str,
        clock: _Clock,
        lock: Lock,
    ):
        self.__client_id = client_id
        self.__rule_appliers: List[_SamplingRuleApplier] = []
        self.__cache_lock = lock
        self.__resource = resource
        self._fallback_sampler = fallback_sampler
        self._clock = clock
        self._last_modified = self._clock.now()

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
        rule_applier: _SamplingRuleApplier
        for rule_applier in self.__rule_appliers:
            if rule_applier.matches(self.__resource, attributes):
                return rule_applier.should_sample(
                    parent_context,
                    trace_id,
                    name,
                    kind=kind,
                    attributes=attributes,
                    links=links,
                    trace_state=trace_state,
                )

        _logger.debug("No sampling rules were matched")
        # Should not ever reach fallback sampler as default rule is able to match
        return self._fallback_sampler.should_sample(
            parent_context,
            trace_id,
            name,
            kind=kind,
            attributes=attributes,
            links=links,
            trace_state=trace_state,
        )

    def update_sampling_rules(
        self, new_sampling_rules: List[_SamplingRule]
    ) -> None:
        new_sampling_rules.sort()
        temp_rule_appliers: List[_SamplingRuleApplier] = []
        for sampling_rule in new_sampling_rules:
            if sampling_rule.RuleName == "":
                _logger.debug(
                    "sampling rule without rule name is not supported"
                )
                continue
            if sampling_rule.Version != 1:
                _logger.debug(
                    "sampling rule without Version 1 is not supported: RuleName: %s",
                    sampling_rule.RuleName,
                )
                continue
            temp_rule_appliers.append(
                _SamplingRuleApplier(
                    sampling_rule, self.__client_id, self._clock
                )
            )

        with self.__cache_lock:
            # map list of rule appliers by each applier's sampling_rule name
            rule_applier_map: Dict[str, _SamplingRuleApplier] = {
                applier.sampling_rule.RuleName: applier
                for applier in self.__rule_appliers
            }

            # If a sampling rule has not changed, keep its respective applier in the cache.
            new_applier: _SamplingRuleApplier
            for index, new_applier in enumerate(temp_rule_appliers):
                rule_name_to_check = new_applier.sampling_rule.RuleName
                if rule_name_to_check in rule_applier_map:
                    old_applier = rule_applier_map[rule_name_to_check]
                    if new_applier.sampling_rule == old_applier.sampling_rule:
                        temp_rule_appliers[index] = old_applier
            self.__rule_appliers = temp_rule_appliers
            self._last_modified = self._clock.now()

    def update_sampling_targets(
        self, sampling_targets_response: _SamplingTargetResponse
    ):
        targets: List[_SamplingTarget] = (
            sampling_targets_response.SamplingTargetDocuments
        )

        with self.__cache_lock:
            next_polling_interval = DEFAULT_TARGET_POLLING_INTERVAL_SECONDS
            min_polling_interval = None

            target_map: Dict[str, _SamplingTarget] = {
                target.RuleName: target for target in targets
            }

            new_appliers: List[_SamplingRuleApplier] = []
            applier: _SamplingRuleApplier
            for applier in self.__rule_appliers:
                if applier.sampling_rule.RuleName in target_map:
                    target = target_map[applier.sampling_rule.RuleName]
                    new_appliers.append(applier.with_target(target))

                    if target.Interval is not None:
                        if (
                            min_polling_interval is None
                            or min_polling_interval > target.Interval
                        ):
                            min_polling_interval = target.Interval
                else:
                    new_appliers.append(applier)

            self.__rule_appliers = new_appliers

            if min_polling_interval is not None:
                next_polling_interval = min_polling_interval

            last_rule_modification = self._clock.from_timestamp(
                sampling_targets_response.LastRuleModification
            )
            refresh_rules = last_rule_modification > self._last_modified

            return (refresh_rules, next_polling_interval)

    def get_all_statistics(self):
        all_statistics: list[dict[str, "str | float | int"]] = []
        applier: _SamplingRuleApplier
        for applier in self.__rule_appliers:
            all_statistics.append(applier.get_then_reset_statistics())
        return all_statistics

    def expired(self) -> bool:
        with self.__cache_lock:
            return (
                self._clock.now()
                > self._last_modified
                + self._clock.time_delta(seconds=CACHE_TTL_SECONDS)
            )
