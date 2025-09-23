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
import json
import os
from unittest import TestCase
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock
from opentelemetry.sdk.extension.aws.trace.sampler._rate_limiting_sampler import (
    _RateLimitingSampler,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_rule import (
    _SamplingRule,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_rule_applier import (
    _SamplingRuleApplier,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_target import (
    _SamplingTarget,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import (
    Decision,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.util.types import Attributes

from ._mock_clock import MockClock

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TEST_DIR, "data")

CLIENT_ID = "12345678901234567890abcd"


# pylint: disable=no-member
class TestSamplingRuleApplier(TestCase):
    def test_applier_attribute_matching_from_xray_response(self):
        default_rule = None
        with open(
            f"{DATA_DIR}/get-sampling-rules-response-sample-2.json",
            encoding="UTF-8",
        ) as file:
            sample_response = json.load(file)
            print(sample_response)
            all_rules = sample_response["SamplingRuleRecords"]
            default_rule = _SamplingRule(**all_rules[0]["SamplingRule"])
            file.close()

        res = Resource.create(
            attributes={
                ResourceAttributes.SERVICE_NAME: "test_service_name",
                ResourceAttributes.CLOUD_PLATFORM: "test_cloud_platform",
            }
        )
        attr: Attributes = {
            SpanAttributes.URL_PATH: "target",
            SpanAttributes.HTTP_REQUEST_METHOD: "method",
            SpanAttributes.URL_FULL: "url",
            SpanAttributes.SERVER_ADDRESS: "host",
            "foo": "bar",
            "abc": "1234",
        }

        rule_applier = _SamplingRuleApplier(default_rule, CLIENT_ID, _Clock())
        self.assertTrue(rule_applier.matches(res, attr))

        # Test again using deprecated Span Attributes
        attr: Attributes = {
            SpanAttributes.HTTP_TARGET: "target",
            SpanAttributes.HTTP_METHOD: "method",
            SpanAttributes.HTTP_URL: "url",
            SpanAttributes.HTTP_HOST: "host",
            "foo": "bar",
            "abc": "1234",
        }
        self.assertTrue(rule_applier.matches(res, attr))

    def test_applier_matches_with_all_attributes(self):
        sampling_rule = _SamplingRule(
            Attributes={"abc": "123", "def": "4?6", "ghi": "*89"},
            FixedRate=0.11,
            HTTPMethod="GET",
            Host="localhost",
            Priority=20,
            ReservoirSize=1,
            # Note that ResourceARN is usually only able to be "*"
            # See: https://docs.aws.amazon.com/xray/latest/devguide/xray-console-sampling.html#xray-console-sampling-options  # noqa: E501
            ResourceARN="arn:aws:lambda:us-west-2:123456789012:function:my-function",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="myServiceName",
            ServiceType="AWS::Lambda::Function",
            URLPath="/helloworld",
            Version=1,
        )

        attributes: Attributes = {
            "server.address": "localhost",
            SpanAttributes.HTTP_REQUEST_METHOD: "GET",
            SpanAttributes.CLOUD_RESOURCE_ID: "arn:aws:lambda:us-west-2:123456789012:function:my-function",
            "url.full": "http://127.0.0.1:5000/helloworld",
            "abc": "123",
            "def": "456",
            "ghi": "789",
            # Test that deprecated attributes are not used in matching when above new attributes are set
            "http.host": "deprecated and will not be used in matching",
            SpanAttributes.HTTP_METHOD: "deprecated and will not be used in matching",
            "faas.id": "deprecated and will not be used in matching",
            "http.url": "deprecated and will not be used in matching",
        }

        resource_attr = {
            ResourceAttributes.SERVICE_NAME: "myServiceName",
            ResourceAttributes.CLOUD_PLATFORM: "aws_lambda",  # CloudPlatformValues.AWS_LAMBDA.value
        }
        resource = Resource.create(attributes=resource_attr)

        rule_applier = _SamplingRuleApplier(sampling_rule, CLIENT_ID, _Clock())
        self.assertTrue(rule_applier.matches(resource, attributes))

        # Test using deprecated Span Attributes
        attributes: Attributes = {
            "http.host": "localhost",
            SpanAttributes.HTTP_METHOD: "GET",
            "faas.id": "arn:aws:lambda:us-west-2:123456789012:function:my-function",
            "http.url": "http://127.0.0.1:5000/helloworld",
            "abc": "123",
            "def": "456",
            "ghi": "789",
        }
        self.assertTrue(rule_applier.matches(resource, attributes))

    def test_applier_wild_card_attributes_matches_span_attributes(self):
        sampling_rule = _SamplingRule(
            Attributes={
                "attr1": "*",
                "attr2": "*",
                "attr3": "HelloWorld",
                "attr4": "Hello*",
                "attr5": "*World",
                "attr6": "?ello*",
                "attr7": "Hell?W*d",
                "attr8": "*.World",
                "attr9": "*.World",
            },
            FixedRate=0.11,
            HTTPMethod="*",
            Host="*",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="*",
            ServiceType="*",
            URLPath="*",
            Version=1,
        )

        attributes: Attributes = {
            "attr1": "",
            "attr2": "HelloWorld",
            "attr3": "HelloWorld",
            "attr4": "HelloWorld",
            "attr5": "HelloWorld",
            "attr6": "HelloWorld",
            "attr7": "HelloWorld",
            "attr8": "Hello.World",
            "attr9": "Bye.World",
        }

        rule_applier = _SamplingRuleApplier(sampling_rule, CLIENT_ID, _Clock())
        self.assertTrue(rule_applier.matches(Resource.get_empty(), attributes))

    def test_applier_wild_card_attributes_matches_http_span_attributes(self):
        sampling_rule = _SamplingRule(
            Attributes={},
            FixedRate=0.11,
            HTTPMethod="*",
            Host="*",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="*",
            ServiceType="*",
            URLPath="*",
            Version=1,
        )

        attributes: Attributes = {
            SpanAttributes.SERVER_ADDRESS: "localhost",
            SpanAttributes.HTTP_REQUEST_METHOD: "GET",
            SpanAttributes.URL_FULL: "http://127.0.0.1:5000/helloworld",
        }

        rule_applier = _SamplingRuleApplier(sampling_rule, CLIENT_ID, _Clock())
        self.assertTrue(rule_applier.matches(Resource.get_empty(), attributes))

        # Test using deprecated Span Attributes
        attributes: Attributes = {
            SpanAttributes.HTTP_HOST: "localhost",
            SpanAttributes.HTTP_METHOD: "GET",
            SpanAttributes.HTTP_URL: "http://127.0.0.1:5000/helloworld",
        }

        self.assertTrue(rule_applier.matches(Resource.get_empty(), attributes))

    def test_applier_wild_card_attributes_matches_with_empty_attributes(self):
        sampling_rule = _SamplingRule(
            Attributes={},
            FixedRate=0.11,
            HTTPMethod="*",
            Host="*",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="*",
            ServiceType="*",
            URLPath="*",
            Version=1,
        )

        attributes: Attributes = {}
        resource_attr: Resource = {
            ResourceAttributes.SERVICE_NAME: "myServiceName",
            ResourceAttributes.CLOUD_PLATFORM: "aws_ec2",
        }
        resource = Resource.create(attributes=resource_attr)

        rule_applier = _SamplingRuleApplier(sampling_rule, CLIENT_ID, _Clock())
        self.assertTrue(rule_applier.matches(resource, attributes))
        self.assertTrue(rule_applier.matches(resource, None))
        self.assertTrue(rule_applier.matches(Resource.get_empty(), attributes))
        self.assertTrue(rule_applier.matches(Resource.get_empty(), None))
        self.assertTrue(rule_applier.matches(None, attributes))
        self.assertTrue(rule_applier.matches(None, None))

    def test_applier_does_not_match_without_http_target(self):
        sampling_rule = _SamplingRule(
            Attributes={},
            FixedRate=0.11,
            HTTPMethod="*",
            Host="*",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="*",
            ServiceType="*",
            URLPath="/helloworld",
            Version=1,
        )

        attributes: Attributes = {}
        resource_attr: Resource = {
            ResourceAttributes.SERVICE_NAME: "myServiceName",
            ResourceAttributes.CLOUD_PLATFORM: "aws_ec2",
        }
        resource = Resource.create(attributes=resource_attr)

        rule_applier = _SamplingRuleApplier(sampling_rule, CLIENT_ID, _Clock())
        self.assertFalse(rule_applier.matches(resource, attributes))

    def test_applier_matches_with_http_target(self):
        sampling_rule = _SamplingRule(
            Attributes={},
            FixedRate=0.11,
            HTTPMethod="*",
            Host="*",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="*",
            ServiceType="*",
            URLPath="/hello*",
            Version=1,
        )

        attributes: Attributes = {SpanAttributes.URL_PATH: "/helloworld"}
        resource_attr: Resource = {
            ResourceAttributes.SERVICE_NAME: "myServiceName",
            ResourceAttributes.CLOUD_PLATFORM: "aws_ec2",
        }
        resource = Resource.create(attributes=resource_attr)

        rule_applier = _SamplingRuleApplier(sampling_rule, CLIENT_ID, _Clock())
        self.assertTrue(rule_applier.matches(resource, attributes))

        # Test again using deprecated Span Attributes
        attributes: Attributes = {SpanAttributes.HTTP_TARGET: "/helloworld"}
        self.assertTrue(rule_applier.matches(resource, attributes))

    def test_applier_matches_with_span_attributes(self):
        sampling_rule = _SamplingRule(
            Attributes={"abc": "123", "def": "456", "ghi": "789"},
            FixedRate=0.11,
            HTTPMethod="*",
            Host="*",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="*",
            ServiceType="*",
            URLPath="*",
            Version=1,
        )

        attributes: Attributes = {
            "server.address": "localhost",
            SpanAttributes.HTTP_REQUEST_METHOD: "GET",
            "url.full": "http://127.0.0.1:5000/helloworld",
            "abc": "123",
            "def": "456",
            "ghi": "789",
        }

        resource_attr: Resource = {
            ResourceAttributes.SERVICE_NAME: "myServiceName",
            ResourceAttributes.CLOUD_PLATFORM: "aws_eks",
        }
        resource = Resource.create(attributes=resource_attr)

        rule_applier = _SamplingRuleApplier(sampling_rule, CLIENT_ID, _Clock())
        self.assertTrue(rule_applier.matches(resource, attributes))

        # Test again using deprecated Span Attributes
        attributes: Attributes = {
            "http.host": "localhost",
            SpanAttributes.HTTP_METHOD: "GET",
            "http.url": "http://127.0.0.1:5000/helloworld",
            "abc": "123",
            "def": "456",
            "ghi": "789",
        }
        self.assertTrue(rule_applier.matches(resource, attributes))

    def test_applier_does_not_match_with_less_span_attributes(self):
        sampling_rule = _SamplingRule(
            Attributes={"abc": "123", "def": "456", "ghi": "789"},
            FixedRate=0.11,
            HTTPMethod="*",
            Host="*",
            Priority=20,
            ReservoirSize=1,
            ResourceARN="*",
            RuleARN="arn:aws:xray:us-east-1:999999999999:sampling-rule/test",
            RuleName="test",
            ServiceName="*",
            ServiceType="*",
            URLPath="*",
            Version=1,
        )

        attributes: Attributes = {
            "http.host": "localhost",
            SpanAttributes.HTTP_REQUEST_METHOD: "GET",
            "url.full": "http://127.0.0.1:5000/helloworld",
            "abc": "123",
        }

        resource_attr: Resource = {
            ResourceAttributes.SERVICE_NAME: "myServiceName",
            ResourceAttributes.CLOUD_PLATFORM: "aws_eks",
        }
        resource = Resource.create(attributes=resource_attr)

        rule_applier = _SamplingRuleApplier(sampling_rule, CLIENT_ID, _Clock())
        self.assertFalse(rule_applier.matches(resource, attributes))

    def test_update_sampling_applier(self):
        sampling_rule = _SamplingRule(
            Attributes={},
            FixedRate=0.11,
            HTTPMethod="*",
            Host="*",
            Priority=20,
            ReservoirSize=1,
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

        rule_applier = _SamplingRuleApplier(
            sampling_rule, CLIENT_ID, mock_clock
        )

        self.assertEqual(
            rule_applier._SamplingRuleApplier__fixed_rate_sampler._rate, 0.11
        )
        self.assertEqual(
            rule_applier._SamplingRuleApplier__reservoir_sampler._RateLimitingSampler__reservoir._quota,
            1,
        )
        self.assertEqual(
            rule_applier._SamplingRuleApplier__reservoir_expiry,
            datetime.datetime.max,
        )

        target = _SamplingTarget(
            FixedRate=1.0,
            Interval=10,
            ReservoirQuota=30,
            ReservoirQuotaTTL=1707764006.0,
            RuleName="test",
        )
        # Update rule applier
        rule_applier = rule_applier.with_target(target)

        time_now = datetime.datetime.fromtimestamp(target.ReservoirQuotaTTL)
        mock_clock.set_time(time_now)

        self.assertEqual(
            rule_applier._SamplingRuleApplier__fixed_rate_sampler._rate, 1.0
        )
        self.assertEqual(
            rule_applier._SamplingRuleApplier__reservoir_sampler._RateLimitingSampler__reservoir._quota,
            30,
        )
        self.assertEqual(
            rule_applier._SamplingRuleApplier__reservoir_expiry,
            mock_clock.now(),
        )

    @staticmethod
    def fake_reservoir_do_sample(*args, **kwargs):
        return SamplingResult(
            decision=Decision.RECORD_AND_SAMPLE,
            attributes=None,
            trace_state=None,
        )

    @staticmethod
    def fake_ratio_do_sample(*args, **kwargs):
        return SamplingResult(
            decision=Decision.RECORD_AND_SAMPLE,
            attributes=None,
            trace_state=None,
        )

    @staticmethod
    def fake_ratio_do_not_sample(*args, **kwargs):
        return SamplingResult(
            decision=Decision.RECORD_AND_SAMPLE,
            attributes=None,
            trace_state=None,
        )

    @patch.object(TraceIdRatioBased, "should_sample", fake_ratio_do_sample)
    @patch.object(
        _RateLimitingSampler, "should_sample", fake_reservoir_do_sample
    )
    def test_populate_and_get_then_reset_statistics(self):
        mock_clock = MockClock()
        rule_applier = _SamplingRuleApplier(
            _SamplingRule(RuleName="test", ReservoirSize=10),
            CLIENT_ID,
            mock_clock,
        )
        rule_applier.should_sample(None, 0, "name")
        rule_applier.should_sample(None, 0, "name")
        rule_applier.should_sample(None, 0, "name")

        statistics = rule_applier.get_then_reset_statistics()

        self.assertEqual(statistics["ClientID"], CLIENT_ID)
        self.assertEqual(statistics["RuleName"], "test")
        self.assertEqual(statistics["Timestamp"], mock_clock.now().timestamp())
        self.assertEqual(statistics["RequestCount"], 3)
        self.assertEqual(statistics["BorrowCount"], 3)
        self.assertEqual(statistics["SampleCount"], 3)
        self.assertEqual(
            rule_applier._SamplingRuleApplier__statistics.RequestCount, 0
        )
        self.assertEqual(
            rule_applier._SamplingRuleApplier__statistics.BorrowCount, 0
        )
        self.assertEqual(
            rule_applier._SamplingRuleApplier__statistics.SampleCount, 0
        )

    def test_should_sample_logic_from_reservoir(self):
        reservoir_size = 10
        time_now = datetime.datetime.fromtimestamp(1707551387.0)
        mock_clock = MockClock(time_now)
        rule_applier = _SamplingRuleApplier(
            _SamplingRule(
                RuleName="test", ReservoirSize=reservoir_size, FixedRate=0.0
            ),
            CLIENT_ID,
            mock_clock,
        )

        mock_clock.add_time(seconds=2.0)
        sampled_count = 0
        for _ in range(0, reservoir_size + 10):
            if (
                rule_applier.should_sample(None, 0, "name").decision
                != Decision.DROP
            ):
                sampled_count += 1
        self.assertEqual(sampled_count, 1)
        # borrow means only 1 sampled

        target = _SamplingTarget(
            FixedRate=0.0,
            Interval=10,
            ReservoirQuota=10,
            ReservoirQuotaTTL=mock_clock.now().timestamp() + 10,
            RuleName="test",
        )
        rule_applier = rule_applier.with_target(target)

        # Use only 100% of quota (10 out of 10), even if 2 seconds have passed
        mock_clock.add_time(seconds=2.0)
        sampled_count = 0
        for _ in range(0, reservoir_size + 10):
            if (
                rule_applier.should_sample(None, 0, "name").decision
                != Decision.DROP
            ):
                sampled_count += 1
        self.assertEqual(sampled_count, reservoir_size)

        # Use only 50% of quota (5 out of 10)
        mock_clock.add_time(seconds=0.5)
        sampled_count = 0
        for _ in range(0, reservoir_size + 10):
            if (
                rule_applier.should_sample(None, 0, "name").decision
                != Decision.DROP
            ):
                sampled_count += 1
        self.assertEqual(sampled_count, 5)

        # Expired at 10s, do not sample
        mock_clock.add_time(seconds=7.5)
        sampled_count = 0
        for _ in range(0, reservoir_size + 10):
            if (
                rule_applier.should_sample(None, 0, "name").decision
                != Decision.DROP
            ):
                sampled_count += 1
        self.assertEqual(sampled_count, 0)
