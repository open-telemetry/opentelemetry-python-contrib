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
