# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_target import (
    _SamplingTargetResponse,
)


class TestSamplingTarget(TestCase):
    def test_sampling_target_response_with_none_inputs(self):
        target_response = _SamplingTargetResponse(None, None, None)
        self.assertEqual(target_response.LastRuleModification, 0.0)
        self.assertEqual(target_response.SamplingTargetDocuments, [])
        self.assertEqual(target_response.UnprocessedStatistics, [])

    def test_sampling_target_response_with_invalid_inputs(self):
        target_response = _SamplingTargetResponse(1.0, [{}], [{}])
        self.assertEqual(target_response.LastRuleModification, 1.0)
        self.assertEqual(len(target_response.SamplingTargetDocuments), 1)
        self.assertEqual(
            target_response.SamplingTargetDocuments[0].FixedRate, 0
        )
        self.assertEqual(
            target_response.SamplingTargetDocuments[0].Interval, None
        )
        self.assertEqual(
            target_response.SamplingTargetDocuments[0].ReservoirQuota, None
        )
        self.assertEqual(
            target_response.SamplingTargetDocuments[0].ReservoirQuotaTTL, None
        )
        self.assertEqual(
            target_response.SamplingTargetDocuments[0].RuleName, ""
        )

        self.assertEqual(len(target_response.UnprocessedStatistics), 1)
        self.assertEqual(
            target_response.UnprocessedStatistics[0].ErrorCode, ""
        )
        self.assertEqual(target_response.UnprocessedStatistics[0].Message, "")
        self.assertEqual(target_response.UnprocessedStatistics[0].RuleName, "")

        target_response = _SamplingTargetResponse(
            1.0, [{"foo": "bar"}], [{"dog": "cat"}]
        )
        self.assertEqual(len(target_response.SamplingTargetDocuments), 0)
        self.assertEqual(len(target_response.UnprocessedStatistics), 0)
