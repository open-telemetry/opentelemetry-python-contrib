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
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_statistics_document import (
    _SamplingStatisticsDocument,
)

from ._mock_clock import MockClock


class TestSamplingStatisticsDocument(TestCase):
    def test_sampling_statistics_document_inputs(self):
        statistics = _SamplingStatisticsDocument("", "")
        self.assertEqual(statistics.ClientID, "")
        self.assertEqual(statistics.RuleName, "")
        self.assertEqual(statistics.BorrowCount, 0)
        self.assertEqual(statistics.SampleCount, 0)
        self.assertEqual(statistics.RequestCount, 0)

        statistics = _SamplingStatisticsDocument(
            "client_id", "rule_name", 1, 2, 3
        )
        self.assertEqual(statistics.ClientID, "client_id")
        self.assertEqual(statistics.RuleName, "rule_name")
        self.assertEqual(statistics.RequestCount, 1)
        self.assertEqual(statistics.BorrowCount, 2)
        self.assertEqual(statistics.SampleCount, 3)

        clock = MockClock(datetime.datetime.fromtimestamp(1707551387.0))
        snapshot = statistics.snapshot(clock)
        self.assertEqual(snapshot.get("ClientID"), "client_id")
        self.assertEqual(snapshot.get("RuleName"), "rule_name")
        self.assertEqual(snapshot.get("Timestamp"), 1707551387.0)
        self.assertEqual(snapshot.get("RequestCount"), 1)
        self.assertEqual(snapshot.get("BorrowCount"), 2)
        self.assertEqual(snapshot.get("SampleCount"), 3)
