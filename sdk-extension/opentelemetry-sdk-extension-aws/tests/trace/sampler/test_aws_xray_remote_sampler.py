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
from logging import DEBUG
from unittest import TestCase
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler.aws_xray_remote_sampler import (
    _AwsXRayRemoteSampler,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import Decision

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

    @patch(
        "opentelemetry.sdk.extension.aws.trace.sampler._aws_xray_sampling_client._AwsXRaySamplingClient.get_sampling_rules",
        return_value=None,
    )
    def test_create_remote_sampler_with_empty_resource(
        self, mocked_get_sampling_rules
    ):
        self.rs = _AwsXRayRemoteSampler(resource=Resource.get_empty())
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

    @patch(
        "opentelemetry.sdk.extension.aws.trace.sampler._aws_xray_sampling_client._AwsXRaySamplingClient.get_sampling_rules",
        return_value=None,
    )
    def test_create_remote_sampler_with_populated_resource(
        self, mocked_get_sampling_rules
    ):
        self.rs = _AwsXRayRemoteSampler(
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

    @patch(
        "opentelemetry.sdk.extension.aws.trace.sampler._aws_xray_sampling_client._AwsXRaySamplingClient.get_sampling_rules",
        return_value=None,
    )
    def test_create_remote_sampler_with_all_fields_populated(
        self, mocked_get_sampling_rules
    ):
        self.rs = _AwsXRayRemoteSampler(
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

    @patch(
        "opentelemetry.sdk.extension.aws.trace.sampler._aws_xray_sampling_client._AwsXRaySamplingClient.get_sampling_rules",
        return_value=None,
    )
    def test_get_description(self, mocked_get_sampling_rules) -> str:
        self.rs: _AwsXRayRemoteSampler = _AwsXRayRemoteSampler(
            resource=Resource.create({"service.name": "dummy_name"})
        )
        self.assertEqual(
            self.rs.get_description(),
            "AwsXRayRemoteSampler{root:ParentBased{root:_InternalAwsXRayRemoteSampler{remote sampling with AWS X-Ray},remoteParentSampled:AlwaysOnSampler,remoteParentNotSampled:AlwaysOffSampler,localParentSampled:AlwaysOnSampler,localParentNotSampled:AlwaysOffSampler}}",  # noqa: E501
        )
