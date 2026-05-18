# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import datetime
from unittest import TestCase

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._rate_limiter import (
    _RateLimiter,
)

from ._mock_clock import MockClock


class TestRateLimiter(TestCase):
    def test_try_spend(self):
        time_now = datetime.datetime.fromtimestamp(1707551387.0)
        clock = MockClock(time_now)
        rate_limiter = _RateLimiter(1, 30, clock)

        spent = 0
        for _ in range(0, 100):
            if rate_limiter.try_spend(1):
                spent += 1
        self.assertEqual(spent, 0)

        spent = 0
        clock.add_time(0.5)
        for _ in range(0, 100):
            if rate_limiter.try_spend(1):
                spent += 1
        self.assertEqual(spent, 15)

        spent = 0
        clock.add_time(1000)
        for _ in range(0, 100):
            if rate_limiter.try_spend(1):
                spent += 1
        self.assertEqual(spent, 30)
