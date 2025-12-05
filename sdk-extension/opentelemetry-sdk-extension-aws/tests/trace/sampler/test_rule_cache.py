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

import datetime
from threading import Lock
from unittest import TestCase

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock
from opentelemetry.sdk.extension.aws.trace.sampler._rule_cache import (
    CACHE_TTL_SECONDS,
    _RuleCache,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_rule import (
    _SamplingRule,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_rule_applier import (
    _SamplingRuleApplier,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_statistics_document import (
    _SamplingStatisticsDocument,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_target import (
    _SamplingTargetResponse,
)
from opentelemetry.sdk.resources import Resource

from ._mock_clock import MockClock

CLIENT_ID = "12345678901234567890abcd"


# pylint: disable=no-member disable=C0103
class TestRuleCache(TestCase):
    def test_cache_update_rules_and_sorts_rules(self):
        cache = _RuleCache(None, None, CLIENT_ID, _Clock(), Lock())
        self.assertTrue(len(cache._RuleCache__rule_appliers) == 0)

        rule1 = _SamplingRule(
            Priority=200, RuleName="only_one_rule", Version=1
        )
        rules = [rule1]
        cache.update_sampling_rules(rules)
        self.assertTrue(len(cache._RuleCache__rule_appliers) == 1)

        rule1 = _SamplingRule(Priority=200, RuleName="abcdef", Version=1)
        rule2 = _SamplingRule(Priority=100, RuleName="abc", Version=1)
        rule3 = _SamplingRule(Priority=100, RuleName="Abc", Version=1)
        rule4 = _SamplingRule(Priority=100, RuleName="ab", Version=1)
        rule5 = _SamplingRule(Priority=100, RuleName="A", Version=1)
        rule6 = _SamplingRule(Priority=1, RuleName="abcdef", Version=1)
        rules = [rule1, rule2, rule3, rule4, rule5, rule6]
        cache.update_sampling_rules(rules)

        self.assertTrue(len(cache._RuleCache__rule_appliers) == 6)
        self.assertEqual(
            cache._RuleCache__rule_appliers[0].sampling_rule.RuleName, "abcdef"
        )
        self.assertEqual(
            cache._RuleCache__rule_appliers[1].sampling_rule.RuleName, "A"
        )
        self.assertEqual(
            cache._RuleCache__rule_appliers[2].sampling_rule.RuleName, "Abc"
        )
        self.assertEqual(
            cache._RuleCache__rule_appliers[3].sampling_rule.RuleName, "ab"
        )
        self.assertEqual(
            cache._RuleCache__rule_appliers[4].sampling_rule.RuleName, "abc"
        )
        self.assertEqual(
            cache._RuleCache__rule_appliers[5].sampling_rule.RuleName, "abcdef"
        )

    def test_rule_cache_expiration_logic(self):
        dt = datetime
        cache = _RuleCache(
            None, Resource.get_empty(), CLIENT_ID, _Clock(), Lock()
        )
        self.assertFalse(cache.expired())
        cache._last_modified = dt.datetime.now() - dt.timedelta(
            seconds=CACHE_TTL_SECONDS - 5
        )
        self.assertFalse(cache.expired())
        cache._last_modified = dt.datetime.now() - dt.timedelta(
            seconds=CACHE_TTL_SECONDS + 1
        )
        self.assertTrue(cache.expired())

    def test_update_cache_with_only_one_rule_changed(self):
        cache = _RuleCache(
            None, Resource.get_empty(), CLIENT_ID, _Clock(), Lock()
        )
        rule1 = _SamplingRule(Priority=1, RuleName="abcdef", Version=1)
        rule2 = _SamplingRule(Priority=10, RuleName="ab", Version=1)
        rule3 = _SamplingRule(Priority=100, RuleName="Abc", Version=1)
        rules = [rule1, rule2, rule3]
        cache.update_sampling_rules(rules)

        cache_rules_copy = cache._RuleCache__rule_appliers

        new_rule3 = _SamplingRule(Priority=5, RuleName="Abc", Version=1)
        rules = [rule1, rule2, new_rule3]
        cache.update_sampling_rules(rules)

        self.assertTrue(len(cache._RuleCache__rule_appliers) == 3)
        self.assertEqual(
            cache._RuleCache__rule_appliers[0].sampling_rule.RuleName, "abcdef"
        )
        self.assertEqual(
            cache._RuleCache__rule_appliers[1].sampling_rule.RuleName, "Abc"
        )
        self.assertEqual(
            cache._RuleCache__rule_appliers[2].sampling_rule.RuleName, "ab"
        )

        # Compare that only rule1 and rule2 objects have not changed due to new_rule3 even after sorting
        self.assertTrue(
            cache_rules_copy[0] is cache._RuleCache__rule_appliers[0]
        )
        self.assertTrue(
            cache_rules_copy[1] is cache._RuleCache__rule_appliers[2]
        )
        self.assertTrue(
            cache_rules_copy[2] is not cache._RuleCache__rule_appliers[1]
        )

    def test_update_rules_removes_older_rule(self):
        cache = _RuleCache(None, None, CLIENT_ID, _Clock(), Lock())
        self.assertTrue(len(cache._RuleCache__rule_appliers) == 0)

        rule1 = _SamplingRule(Priority=200, RuleName="first_rule", Version=1)
        rules = [rule1]
        cache.update_sampling_rules(rules)
        self.assertTrue(len(cache._RuleCache__rule_appliers) == 1)
        self.assertEqual(
            cache._RuleCache__rule_appliers[0].sampling_rule.RuleName,
            "first_rule",
        )

        rule1 = _SamplingRule(Priority=200, RuleName="second_rule", Version=1)
        rules = [rule1]
        cache.update_sampling_rules(rules)
        self.assertTrue(len(cache._RuleCache__rule_appliers) == 1)
        self.assertEqual(
            cache._RuleCache__rule_appliers[0].sampling_rule.RuleName,
            "second_rule",
        )

    def test_update_sampling_targets(self):
        sampling_rule_1 = _SamplingRule(
            Attributes={},
            FixedRate=0.05,
            HTTPMethod="*",
            Host="*",
            Priority=10000,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/default",
            RuleName="default",
            ServiceName="*",
            ServiceType="*",
            URLPath="*",
            Version=1,
        )

        sampling_rule_2 = _SamplingRule(
            Attributes={},
            FixedRate=0.20,
            HTTPMethod="*",
            Host="*",
            Priority=20,
            ReservoirSize=10,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="*",
            ServiceType="*",
            URLPath="*",
            Version=1,
        )

        time_now = datetime.datetime.fromtimestamp(1707551387.0)
        mock_clock = MockClock(time_now)

        rule_cache = _RuleCache(
            Resource.get_empty(), None, "", mock_clock, Lock()
        )
        rule_cache.update_sampling_rules([sampling_rule_1, sampling_rule_2])

        # quota should be 1 because of borrowing=true until targets are updated
        rule_applier_0 = rule_cache._RuleCache__rule_appliers[0]
        self.assertEqual(
            rule_applier_0._SamplingRuleApplier__reservoir_sampler._RateLimitingSampler__reservoir._quota,
            1,
        )
        self.assertEqual(
            rule_applier_0._SamplingRuleApplier__fixed_rate_sampler._rate,
            sampling_rule_2.FixedRate,
        )

        rule_applier_1 = rule_cache._RuleCache__rule_appliers[1]
        self.assertEqual(
            rule_applier_1._SamplingRuleApplier__reservoir_sampler._RateLimitingSampler__reservoir._quota,
            1,
        )
        self.assertEqual(
            rule_applier_1._SamplingRuleApplier__fixed_rate_sampler._rate,
            sampling_rule_1.FixedRate,
        )

        target_1 = {
            "FixedRate": 0.05,
            "Interval": 15,
            "ReservoirQuota": 1,
            "ReservoirQuotaTTL": mock_clock.now().timestamp() + 10,
            "RuleName": "default",
        }
        target_2 = {
            "FixedRate": 0.15,
            "Interval": 12,
            "ReservoirQuota": 5,
            "ReservoirQuotaTTL": mock_clock.now().timestamp() + 10,
            "RuleName": "test",
        }
        target_3 = {
            "FixedRate": 0.15,
            "Interval": 3,
            "ReservoirQuota": 5,
            "ReservoirQuotaTTL": mock_clock.now().timestamp() + 10,
            "RuleName": "associated rule does not exist",
        }
        target_response = _SamplingTargetResponse(
            mock_clock.now().timestamp() - 10,
            [target_1, target_2, target_3],
            [],
        )
        refresh_rules, min_polling_interval = (
            rule_cache.update_sampling_targets(target_response)
        )
        self.assertFalse(refresh_rules)
        # target_3 Interval is ignored since it's not associated with a Rule Applier
        self.assertEqual(min_polling_interval, target_2["Interval"])

        # still only 2 rule appliers should exist if for some reason 3 targets are obtained
        self.assertEqual(len(rule_cache._RuleCache__rule_appliers), 2)

        # borrowing=false, use quota from targets
        rule_applier_0 = rule_cache._RuleCache__rule_appliers[0]
        self.assertEqual(
            rule_applier_0._SamplingRuleApplier__reservoir_sampler._RateLimitingSampler__reservoir._quota,
            target_2["ReservoirQuota"],
        )
        self.assertEqual(
            rule_applier_0._SamplingRuleApplier__fixed_rate_sampler._rate,
            target_2["FixedRate"],
        )

        rule_applier_1 = rule_cache._RuleCache__rule_appliers[1]
        self.assertEqual(
            rule_applier_1._SamplingRuleApplier__reservoir_sampler._RateLimitingSampler__reservoir._quota,
            target_1["ReservoirQuota"],
        )
        self.assertEqual(
            rule_applier_1._SamplingRuleApplier__fixed_rate_sampler._rate,
            target_1["FixedRate"],
        )

        # Test target response modified after Rule cache's last modified date
        target_response.LastRuleModification = mock_clock.now().timestamp() + 1
        refresh_rules, _ = rule_cache.update_sampling_targets(target_response)
        self.assertTrue(refresh_rules)

    # pylint:disable=C0103
    def test_get_all_statistics(self):
        time_now = datetime.datetime.fromtimestamp(1707551387.0)
        mock_clock = MockClock(time_now)
        rule_applier_1 = _SamplingRuleApplier(
            _SamplingRule(RuleName="test"), CLIENT_ID, mock_clock
        )
        rule_applier_2 = _SamplingRuleApplier(
            _SamplingRule(RuleName="default"), CLIENT_ID, mock_clock
        )

        rule_applier_1._SamplingRuleApplier__statistics = (
            _SamplingStatisticsDocument(CLIENT_ID, "test", 4, 2, 2)
        )
        rule_applier_2._SamplingRuleApplier__statistics = (
            _SamplingStatisticsDocument(CLIENT_ID, "default", 5, 5, 5)
        )

        rule_cache = _RuleCache(
            Resource.get_empty(), None, "", mock_clock, Lock()
        )
        rule_cache._RuleCache__rule_appliers = [rule_applier_1, rule_applier_2]

        mock_clock.add_time(10)
        statistics = rule_cache.get_all_statistics()

        self.assertEqual(
            statistics,
            [
                {
                    "ClientID": CLIENT_ID,
                    "RuleName": "test",
                    "Timestamp": mock_clock.now().timestamp(),
                    "RequestCount": 4,
                    "BorrowCount": 2,
                    "SampleCount": 2,
                },
                {
                    "ClientID": CLIENT_ID,
                    "RuleName": "default",
                    "Timestamp": mock_clock.now().timestamp(),
                    "RequestCount": 5,
                    "BorrowCount": 5,
                    "SampleCount": 5,
                },
            ],
        )
