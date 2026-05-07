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
from unittest import TestCase

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._rate_limiting_sampler import (
    _RateLimitingSampler,
)
from opentelemetry.sdk.trace.sampling import Decision

from ._mock_clock import MockClock


class TestRateLimitingSampler(TestCase):
    def test_should_sample(self):
        time_now = datetime.datetime.fromtimestamp(1707551387.0)
        clock = MockClock(time_now)
        sampler = _RateLimitingSampler(30, clock)

        # Essentially the same tests as test_rate_limiter.py
        sampled = 0
        for _ in range(0, 100):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 0)

        sampled = 0
        clock.add_time(0.5)
        for _ in range(0, 100):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 15)

        sampled = 0
        clock.add_time(1.0)
        for _ in range(0, 100):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 30)

        sampled = 0
        clock.add_time(2.5)
        for _ in range(0, 100):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 30)

        sampled = 0
        clock.add_time(1000)
        for _ in range(0, 100):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 30)

    def test_should_sample_with_quota_of_one(self):
        time_now = datetime.datetime.fromtimestamp(1707551387.0)
        clock = MockClock(time_now)
        sampler = _RateLimitingSampler(1, clock)

        sampled = 0
        for _ in range(0, 50):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 0)

        sampled = 0
        clock.add_time(0.5)
        for _ in range(0, 50):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 0)

        sampled = 0
        clock.add_time(0.5)
        for _ in range(0, 50):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 1)

        sampled = 0
        clock.add_time(1000)
        for _ in range(0, 50):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 1)
