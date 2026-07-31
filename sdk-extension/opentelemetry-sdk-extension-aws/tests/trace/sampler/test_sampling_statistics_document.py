# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

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
