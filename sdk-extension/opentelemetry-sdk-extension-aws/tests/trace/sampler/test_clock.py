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
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock


class TestClock(TestCase):
    def test_from_timestamp(self):
        pass

    def test_time_delta(self):
        clock = _Clock()
        dt = clock.from_timestamp(1707551387.0)
        delta = clock.time_delta(3600)
        new_dt = dt + delta
        self.assertTrue(new_dt.timestamp() - dt.timestamp() == 3600)
