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

from opentelemetry.samplers.aws._sampling_target import _SamplingTargetResponse


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
