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

from unittest import TestCase

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_rule import (
    _SamplingRule,
)


class TestSamplingRule(TestCase):
    def test_sampling_rule_ordering(self):
        rule1 = _SamplingRule(Priority=1, RuleName="abcdef", Version=1)
        rule2 = _SamplingRule(Priority=100, RuleName="A", Version=1)
        rule3 = _SamplingRule(Priority=100, RuleName="Abc", Version=1)
        rule4 = _SamplingRule(Priority=100, RuleName="ab", Version=1)
        rule5 = _SamplingRule(Priority=100, RuleName="abc", Version=1)
        rule6 = _SamplingRule(Priority=200, RuleName="abcdef", Version=1)

        self.assertTrue(rule1 < rule2 < rule3 < rule4 < rule5 < rule6)

    def test_sampling_rule_equality(self):
        sampling_rule = _SamplingRule(
            Attributes={"abc": "123", "def": "4?6", "ghi": "*89"},
            FixedRate=0.11,
            HTTPMethod="GET",
            Host="localhost",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="myServiceName",
            ServiceType="AWS::EKS::Container",
            URLPath="/helloworld",
            Version=1,
        )

        sampling_rule_attr_unordered = _SamplingRule(
            Attributes={"ghi": "*89", "abc": "123", "def": "4?6"},
            FixedRate=0.11,
            HTTPMethod="GET",
            Host="localhost",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="myServiceName",
            ServiceType="AWS::EKS::Container",
            URLPath="/helloworld",
            Version=1,
        )

        self.assertTrue(sampling_rule == sampling_rule_attr_unordered)

        sampling_rule_updated = _SamplingRule(
            Attributes={"ghi": "*89", "abc": "123", "def": "4?6"},
            FixedRate=0.11,
            HTTPMethod="GET",
            Host="localhost",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="myServiceName",
            ServiceType="AWS::EKS::Container",
            URLPath="/helloworld_new",
            Version=1,
        )

        sampling_rule_updated_2 = _SamplingRule(
            Attributes={"abc": "128", "def": "4?6", "ghi": "*89"},
            FixedRate=0.11,
            HTTPMethod="GET",
            Host="localhost",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="myServiceName",
            ServiceType="AWS::EKS::Container",
            URLPath="/helloworld",
            Version=1,
        )

        self.assertFalse(sampling_rule == sampling_rule_updated)
        self.assertFalse(sampling_rule == sampling_rule_updated_2)
