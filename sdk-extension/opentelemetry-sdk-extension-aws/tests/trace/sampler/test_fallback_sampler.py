# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import datetime
from unittest import TestCase

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._fallback_sampler import (
    _FallbackSampler,
)
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, Decision

from ._mock_clock import MockClock


class TestRateLimitingSampler(TestCase):
    # pylint: disable=too-many-branches
    def test_should_sample(self):
        time_now = datetime.datetime.fromtimestamp(1707551387.0)
        clock = MockClock(time_now)
        sampler = _FallbackSampler(clock)
        # Ignore testing TraceIdRatioBased
        sampler._FallbackSampler__fixed_rate_sampler = ALWAYS_OFF

        sampler.should_sample(None, 1234, "name")

        # Essentially the same tests as test_rate_limiter.py

        # 0 seconds passed, 0 quota available
        sampled = 0
        for _ in range(0, 30):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 0)

        # 0.4 seconds passed, 0.4 quota available
        sampled = 0
        clock.add_time(0.4)
        for _ in range(0, 30):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 0)

        # 0.8 seconds passed, 0.8 quota available
        sampled = 0
        clock.add_time(0.4)
        for _ in range(0, 30):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 0)

        # 1.2 seconds passed, 1 quota consumed, 0 quota available
        sampled = 0
        clock.add_time(0.4)
        for _ in range(0, 30):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 1)

        # 1.6 seconds passed, 0.4 quota available
        sampled = 0
        clock.add_time(0.4)
        for _ in range(0, 30):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 0)

        # 2.0 seconds passed, 0.8 quota available
        sampled = 0
        clock.add_time(0.4)
        for _ in range(0, 30):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 0)

        # 2.4 seconds passed, one more quota consumed, 0 quota available
        sampled = 0
        clock.add_time(0.4)
        for _ in range(0, 30):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 1)

        # 30 seconds passed, only one quota can be consumed
        sampled = 0
        clock.add_time(100)
        for _ in range(0, 30):
            if (
                sampler.should_sample(None, 1234, "name").decision
                != Decision.DROP
            ):
                sampled += 1
        self.assertEqual(sampled, 1)
