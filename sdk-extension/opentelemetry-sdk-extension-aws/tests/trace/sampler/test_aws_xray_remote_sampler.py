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

import json
import os
import threading
import time
from logging import DEBUG
from unittest import TestCase
from unittest.mock import patch

from pytest import mark

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler.aws_xray_remote_sampler import (
    AwsXRayRemoteSampler,
    _InternalAwsXRayRemoteSampler,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Tracer, TracerProvider
from opentelemetry.sdk.trace.sampling import Decision

from ._mock_clock import MockClock

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TEST_DIR, "data")


def create_spans(
    sampled_array, thread_id, span_attributes, remote_sampler, number_of_spans
):
    sampled = 0
    for _ in range(0, number_of_spans):
        if (
            remote_sampler.should_sample(
                None, 0, "name", attributes=span_attributes
            ).decision
            != Decision.DROP
        ):
            sampled += 1
    sampled_array[thread_id] = sampled


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code):
            self.json_data = json_data
            self.status_code = status_code

        def json(self):
            return self.json_data

    if kwargs["url"] == "http://127.0.0.1:2000/GetSamplingRules":
        with open(
            f"{DATA_DIR}/test-remote-sampler_sampling-rules-response-sample.json",
            encoding="UTF-8",
        ) as file:
            sample_response = json.load(file)
            file.close()
        return MockResponse(sample_response, 200)
    if kwargs["url"] == "http://127.0.0.1:2000/SamplingTargets":
        with open(
            f"{DATA_DIR}/test-remote-sampler_sampling-targets-response-sample.json",
            encoding="UTF-8",
        ) as file:
            sample_response = json.load(file)
            file.close()
        return MockResponse(sample_response, 200)
    return MockResponse(None, 404)


class TestAwsXRayRemoteSampler(TestCase):
    def setUp(self):
        self.rs = None

    def tearDown(self):
        # Clean up timers
        if self.rs is not None:
            self.rs._root._root._rules_timer.cancel()
            self.rs._root._root._targets_timer.cancel()

    def test_create_remote_sampler_with_empty_resource(self):
        self.rs = AwsXRayRemoteSampler(resource=Resource.get_empty())
        self.assertIsNotNone(self.rs._root._root._rules_timer)
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__polling_interval,
            300,
        )
        self.assertIsNotNone(
            self.rs._root._root._InternalAwsXRayRemoteSampler__xray_client
        )
        self.assertIsNotNone(
            self.rs._root._root._InternalAwsXRayRemoteSampler__resource
        )
        self.assertTrue(
            len(self.rs._root._root._InternalAwsXRayRemoteSampler__client_id),
            24,
        )

    def test_create_remote_sampler_with_populated_resource(self):
        self.rs = AwsXRayRemoteSampler(
            resource=Resource.create(
                {
                    "service.name": "test-service-name",
                    "cloud.platform": "test-cloud-platform",
                }
            )
        )
        self.assertIsNotNone(self.rs._root._root._rules_timer)
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__polling_interval,
            300,
        )
        self.assertIsNotNone(
            self.rs._root._root._InternalAwsXRayRemoteSampler__xray_client
        )
        self.assertIsNotNone(
            self.rs._root._root._InternalAwsXRayRemoteSampler__resource
        )
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__resource.attributes[
                "service.name"
            ],
            "test-service-name",
        )
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__resource.attributes[
                "cloud.platform"
            ],
            "test-cloud-platform",
        )

    def test_create_remote_sampler_with_all_fields_populated(self):
        self.rs = AwsXRayRemoteSampler(
            resource=Resource.create(
                {
                    "service.name": "test-service-name",
                    "cloud.platform": "test-cloud-platform",
                }
            ),
            endpoint="http://abc.com",
            polling_interval=120,
            log_level=DEBUG,
        )
        self.assertIsNotNone(self.rs._root._root._rules_timer)
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__polling_interval,
            120,
        )
        self.assertIsNotNone(
            self.rs._root._root._InternalAwsXRayRemoteSampler__xray_client
        )
        self.assertIsNotNone(
            self.rs._root._root._InternalAwsXRayRemoteSampler__resource
        )
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__xray_client._AwsXRaySamplingClient__get_sampling_rules_endpoint,
            "http://abc.com/GetSamplingRules",
        )
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__resource.attributes[
                "service.name"
            ],
            "test-service-name",
        )
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__resource.attributes[
                "cloud.platform"
            ],
            "test-cloud-platform",
        )

    @patch("requests.Session.post", side_effect=mocked_requests_get)
    @patch(
        "opentelemetry.sdk.extension.aws.trace.sampler.aws_xray_remote_sampler.DEFAULT_TARGET_POLLING_INTERVAL_SECONDS",
        2,
    )
    def test_update_sampling_rules_and_targets_with_pollers_and_should_sample(
        self, mock_post=None
    ):
        self.rs = AwsXRayRemoteSampler(
            resource=Resource.create(
                {
                    "service.name": "test-service-name",
                    "cloud.platform": "test-cloud-platform",
                }
            )
        )
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__target_polling_interval,
            2,
        )

        time.sleep(1.0)
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__rule_cache._RuleCache__rule_appliers[
                0
            ].sampling_rule.RuleName,
            "test",
        )
        self.assertEqual(
            self.rs.should_sample(
                None, 0, "name", attributes={"abc": "1234"}
            ).decision,
            Decision.DROP,
        )

        # wait 2 more seconds since targets polling was patched to 2 seconds (rather than 10s)
        time.sleep(2.0)
        self.assertEqual(
            self.rs._root._root._InternalAwsXRayRemoteSampler__target_polling_interval,
            1000,
        )
        self.assertEqual(
            self.rs.should_sample(
                None, 0, "name", attributes={"abc": "1234"}
            ).decision,
            Decision.RECORD_AND_SAMPLE,
        )
        self.assertEqual(
            self.rs.should_sample(
                None, 0, "name", attributes={"abc": "1234"}
            ).decision,
            Decision.RECORD_AND_SAMPLE,
        )
        self.assertEqual(
            self.rs.should_sample(
                None, 0, "name", attributes={"abc": "1234"}
            ).decision,
            Decision.RECORD_AND_SAMPLE,
        )

    @mark.skip(
        reason="Uses sleep in test, which could be flaky. Remove this skip for validation locally."
    )
    @patch("requests.Session.post", side_effect=mocked_requests_get)
    @patch(
        "opentelemetry.sdk.extension.aws.trace.sampler.aws_xray_remote_sampler.DEFAULT_TARGET_POLLING_INTERVAL_SECONDS",
        3,
    )
    def test_multithreading_with_large_reservoir_with_otel_sdk(
        self, mock_post=None
    ):
        self.rs = AwsXRayRemoteSampler(
            resource=Resource.create(
                {
                    "service.name": "test-service-name",
                    "cloud.platform": "test-cloud-platform",
                }
            )
        )
        attributes = {"abc": "1234"}

        time.sleep(2.0)
        self.assertEqual(
            self.rs.should_sample(
                None, 0, "name", attributes=attributes
            ).decision,
            Decision.DROP,
        )

        # wait 3 more seconds since targets polling was patched to 2 seconds (rather than 10s)
        time.sleep(3.0)

        number_of_spans = 100
        thread_count = 1000
        sampled_array = []
        threads = []

        for idx in range(0, thread_count):
            sampled_array.append(0)
            threads.append(
                threading.Thread(
                    target=create_spans,
                    name="thread_" + str(idx),
                    daemon=True,
                    args=(
                        sampled_array,
                        idx,
                        attributes,
                        self.rs,
                        number_of_spans,
                    ),
                )
            )
            threads[idx].start()
        sum_sampled = 0

        for idx in range(0, thread_count):
            threads[idx].join()
            sum_sampled += sampled_array[idx]

        test_rule_applier = self.rs._root._root._InternalAwsXRayRemoteSampler__rule_cache._RuleCache__rule_appliers[
            0
        ]
        self.assertEqual(
            test_rule_applier._SamplingRuleApplier__reservoir_sampler._RateLimitingSampler__reservoir._quota,
            100000,
        )
        self.assertEqual(sum_sampled, 100000)

    # pylint: disable=no-member
    @mark.skip(
        reason="Uses sleep in test, which could be flaky. Remove this skip for validation locally."
    )
    @patch("requests.Session.post", side_effect=mocked_requests_get)
    @patch(
        "opentelemetry.sdk.extension.aws.trace.sampler.aws_xray_remote_sampler.DEFAULT_TARGET_POLLING_INTERVAL_SECONDS",
        2,
    )
    @patch(
        "opentelemetry.sdk.extension.aws.trace.sampler.aws_xray_remote_sampler._Clock",
        MockClock,
    )
    def test_multithreading_with_some_reservoir_with_otel_sdk(
        self, mock_post=None
    ):
        self.rs = AwsXRayRemoteSampler(
            resource=Resource.create(
                {
                    "service.name": "test-service-name",
                    "cloud.platform": "test-cloud-platform",
                }
            )
        )
        attributes = {"abc": "non-matching attribute value, use default rule"}

        # Using normal clock, finishing all thread jobs will take more than a second,
        # which will eat up more than 1 second of reservoir. Using MockClock we can freeze time
        # and pretend all thread jobs start and end at the exact same time,
        # assume and test exactly 1 second of reservoir (100 quota) only
        mock_clock: MockClock = self.rs._root._root._clock

        time.sleep(1.0)
        mock_clock.add_time(1.0)
        self.assertEqual(mock_clock.now(), self.rs._root._root._clock.now())
        self.assertEqual(
            self.rs.should_sample(
                None, 0, "name", attributes=attributes
            ).decision,
            Decision.RECORD_AND_SAMPLE,
        )

        # wait 2 more seconds since targets polling was patched to 2 seconds (rather than 10s)
        time.sleep(2.0)
        mock_clock.add_time(2.0)
        self.assertEqual(mock_clock.now(), self.rs._root._root._clock.now())

        number_of_spans = 100
        thread_count = 1000
        sampled_array = []
        threads = []

        for idx in range(0, thread_count):
            sampled_array.append(0)
            threads.append(
                threading.Thread(
                    target=create_spans,
                    name="thread_" + str(idx),
                    daemon=True,
                    args=(
                        sampled_array,
                        idx,
                        attributes,
                        self.rs,
                        number_of_spans,
                    ),
                )
            )
            threads[idx].start()

        sum_sampled = 0
        for idx in range(0, thread_count):
            threads[idx].join()
            sum_sampled += sampled_array[idx]

        default_rule_applier = self.rs._root._root._InternalAwsXRayRemoteSampler__rule_cache._RuleCache__rule_appliers[
            1
        ]
        self.assertEqual(
            default_rule_applier._SamplingRuleApplier__reservoir_sampler._RateLimitingSampler__reservoir._quota,
            100,
        )
        self.assertEqual(sum_sampled, 100)

    def test_get_description(self) -> str:
        self.rs: AwsXRayRemoteSampler = AwsXRayRemoteSampler(
            resource=Resource.create({"service.name": "dummy_name"})
        )
        self.assertEqual(
            self.rs.get_description(),
            "AwsXRayRemoteSampler{root:ParentBased{root:_InternalAwsXRayRemoteSampler{remote sampling with AWS X-Ray},remoteParentSampled:AlwaysOnSampler,remoteParentNotSampled:AlwaysOffSampler,localParentSampled:AlwaysOnSampler,localParentNotSampled:AlwaysOffSampler}}",  # noqa: E501
        )

    @patch("requests.Session.post", side_effect=mocked_requests_get)
    def test_parent_based_xray_sampler_updates_statistics_once_for_one_parent_span_with_two_children(
        self, mock_post=None
    ):
        self.rs: AwsXRayRemoteSampler = AwsXRayRemoteSampler(
            resource=Resource.create(
                {"service.name": "use-default-sample-all-rule"}
            )
        )
        time.sleep(1.0)

        provider = TracerProvider(sampler=self.rs)
        tracer: Tracer = provider.get_tracer("test_tracer_1")

        # child1 and child2 are child spans of root parent0
        # For AwsXRayRemoteSampler (ParentBased), expect only parent0 to update statistics
        with tracer.start_as_current_span("parent0") as _:
            with tracer.start_as_current_span("child1") as _:
                pass
            with tracer.start_as_current_span("child2") as _:
                pass
        default_rule_applier = self.rs._root._root._InternalAwsXRayRemoteSampler__rule_cache._RuleCache__rule_appliers[
            1
        ]
        self.assertEqual(
            default_rule_applier._SamplingRuleApplier__statistics.RequestCount,
            1,
        )
        self.assertEqual(
            default_rule_applier._SamplingRuleApplier__statistics.SampleCount,
            1,
        )

    @patch("requests.Session.post", side_effect=mocked_requests_get)
    def test_non_parent_based_xray_sampler_updates_statistics_thrice_for_one_parent_span_with_two_children(
        self, mock_post=None
    ):
        non_parent_based_xray_sampler: _InternalAwsXRayRemoteSampler = (
            _InternalAwsXRayRemoteSampler(
                resource=Resource.create(
                    {"service.name": "use-default-sample-all-rule"}
                )
            )
        )
        time.sleep(1.0)

        provider = TracerProvider(sampler=non_parent_based_xray_sampler)
        tracer: Tracer = provider.get_tracer("test_tracer_2")

        # child1 and child2 are child spans of root parent0
        # For _InternalAwsXRayRemoteSampler (Non-ParentBased), expect all 3 spans to update statistics
        with tracer.start_as_current_span("parent0") as _:
            with tracer.start_as_current_span("child1") as _:
                pass
            with tracer.start_as_current_span("child2") as _:
                pass
        default_rule_applier = non_parent_based_xray_sampler._InternalAwsXRayRemoteSampler__rule_cache._RuleCache__rule_appliers[
            1
        ]
        self.assertEqual(
            default_rule_applier._SamplingRuleApplier__statistics.RequestCount,
            3,
        )
        self.assertEqual(
            default_rule_applier._SamplingRuleApplier__statistics.SampleCount,
            3,
        )

        non_parent_based_xray_sampler._rules_timer.cancel()
        non_parent_based_xray_sampler._targets_timer.cancel()
