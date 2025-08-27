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
from logging import getLogger
from unittest import TestCase
from unittest.mock import patch

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._aws_xray_sampling_client import (
    _AwsXRaySamplingClient,
)

SAMPLING_CLIENT_LOGGER_NAME = (
    "opentelemetry.sdk.extension.aws.trace.sampler._aws_xray_sampling_client"
)
_sampling_client_logger = getLogger(SAMPLING_CLIENT_LOGGER_NAME)

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TEST_DIR, "data")


class TestAwsXRaySamplingClient(TestCase):
    @patch("requests.Session.post")
    def test_get_no_sampling_rules(self, mock_post=None):
        mock_post.return_value.configure_mock(
            **{"json.return_value": {"SamplingRuleRecords": []}}
        )
        client = _AwsXRaySamplingClient("http://127.0.0.1:2000")
        sampling_rules = client.get_sampling_rules()
        self.assertTrue(len(sampling_rules) == 0)

    @patch("requests.Session.post")
    def test_get_invalid_responses(self, mock_post=None):
        mock_post.return_value.configure_mock(**{"json.return_value": {}})
        client = _AwsXRaySamplingClient("http://127.0.0.1:2000")
        with self.assertLogs(_sampling_client_logger, level="ERROR"):
            sampling_rules = client.get_sampling_rules()
            self.assertTrue(len(sampling_rules) == 0)

    @patch("requests.Session.post")
    def test_get_sampling_rule_missing_in_records(self, mock_post=None):
        mock_post.return_value.configure_mock(
            **{"json.return_value": {"SamplingRuleRecords": [{}]}}
        )
        client = _AwsXRaySamplingClient("http://127.0.0.1:2000")
        with self.assertLogs(_sampling_client_logger, level="ERROR"):
            sampling_rules = client.get_sampling_rules()
            self.assertTrue(len(sampling_rules) == 0)

    @patch("requests.Session.post")
    def test_default_values_used_when_missing_properties_in_sampling_rule(
        self, mock_post=None
    ):
        mock_post.return_value.configure_mock(
            **{
                "json.return_value": {
                    "SamplingRuleRecords": [{"SamplingRule": {}}]
                }
            }
        )
        client = _AwsXRaySamplingClient("http://127.0.0.1:2000")
        sampling_rules = client.get_sampling_rules()
        self.assertTrue(len(sampling_rules) == 1)

        sampling_rule = sampling_rules[0]
        self.assertEqual(sampling_rule.Attributes, {})
        self.assertEqual(sampling_rule.FixedRate, 0.0)
        self.assertEqual(sampling_rule.HTTPMethod, "")
        self.assertEqual(sampling_rule.Host, "")
        self.assertEqual(sampling_rule.Priority, 10001)
        self.assertEqual(sampling_rule.ReservoirSize, 0)
        self.assertEqual(sampling_rule.ResourceARN, "")
        self.assertEqual(sampling_rule.RuleARN, "")
        self.assertEqual(sampling_rule.RuleName, "")
        self.assertEqual(sampling_rule.ServiceName, "")
        self.assertEqual(sampling_rule.ServiceType, "")
        self.assertEqual(sampling_rule.URLPath, "")
        self.assertEqual(sampling_rule.Version, 0)

    @patch("requests.Session.post")
    def test_get_correct_number_of_sampling_rules(self, mock_post=None):
        sampling_records = []
        with open(
            f"{DATA_DIR}/get-sampling-rules-response-sample.json",
            encoding="UTF-8",
        ) as file:
            sample_response = json.load(file)
            sampling_records = sample_response["SamplingRuleRecords"]
            mock_post.return_value.configure_mock(
                **{"json.return_value": sample_response}
            )
            file.close()
        client = _AwsXRaySamplingClient("http://127.0.0.1:2000")
        sampling_rules = client.get_sampling_rules()
        self.assertEqual(len(sampling_rules), 3)
        self.assertEqual(len(sampling_rules), len(sampling_records))
        self.validate_match_sampling_rules_properties_with_records(
            sampling_rules, sampling_records
        )

    def validate_match_sampling_rules_properties_with_records(
        self, sampling_rules, sampling_records
    ):
        for _, (sampling_rule, sampling_record) in enumerate(
            zip(sampling_rules, sampling_records)
        ):
            self.assertIsNotNone(sampling_rule.Attributes)
            self.assertEqual(
                sampling_rule.Attributes,
                sampling_record["SamplingRule"]["Attributes"],
            )
            self.assertIsNotNone(sampling_rule.FixedRate)
            self.assertEqual(
                sampling_rule.FixedRate,
                sampling_record["SamplingRule"]["FixedRate"],
            )
            self.assertIsNotNone(sampling_rule.HTTPMethod)
            self.assertEqual(
                sampling_rule.HTTPMethod,
                sampling_record["SamplingRule"]["HTTPMethod"],
            )
            self.assertIsNotNone(sampling_rule.Host)
            self.assertEqual(
                sampling_rule.Host, sampling_record["SamplingRule"]["Host"]
            )
            self.assertIsNotNone(sampling_rule.Priority)
            self.assertEqual(
                sampling_rule.Priority,
                sampling_record["SamplingRule"]["Priority"],
            )
            self.assertIsNotNone(sampling_rule.ReservoirSize)
            self.assertEqual(
                sampling_rule.ReservoirSize,
                sampling_record["SamplingRule"]["ReservoirSize"],
            )
            self.assertIsNotNone(sampling_rule.ResourceARN)
            self.assertEqual(
                sampling_rule.ResourceARN,
                sampling_record["SamplingRule"]["ResourceARN"],
            )
            self.assertIsNotNone(sampling_rule.RuleARN)
            self.assertEqual(
                sampling_rule.RuleARN,
                sampling_record["SamplingRule"]["RuleARN"],
            )
            self.assertIsNotNone(sampling_rule.RuleName)
            self.assertEqual(
                sampling_rule.RuleName,
                sampling_record["SamplingRule"]["RuleName"],
            )
            self.assertIsNotNone(sampling_rule.ServiceName)
            self.assertEqual(
                sampling_rule.ServiceName,
                sampling_record["SamplingRule"]["ServiceName"],
            )
            self.assertIsNotNone(sampling_rule.ServiceType)
            self.assertEqual(
                sampling_rule.ServiceType,
                sampling_record["SamplingRule"]["ServiceType"],
            )
            self.assertIsNotNone(sampling_rule.URLPath)
            self.assertEqual(
                sampling_rule.URLPath,
                sampling_record["SamplingRule"]["URLPath"],
            )
            self.assertIsNotNone(sampling_rule.Version)
            self.assertEqual(
                sampling_rule.Version,
                sampling_record["SamplingRule"]["Version"],
            )

    @patch("requests.Session.post")
    def test_get_sampling_targets(self, mock_post=None):
        with open(
            f"{DATA_DIR}/get-sampling-targets-response-sample.json",
            encoding="UTF-8",
        ) as file:
            sample_response = json.load(file)
            mock_post.return_value.configure_mock(
                **{"json.return_value": sample_response}
            )
            file.close()
        client = _AwsXRaySamplingClient("http://127.0.0.1:2000")
        sampling_targets_response = client.get_sampling_targets(statistics=[])
        self.assertEqual(
            len(sampling_targets_response.SamplingTargetDocuments), 2
        )
        self.assertEqual(
            len(sampling_targets_response.UnprocessedStatistics), 0
        )
        self.assertEqual(
            sampling_targets_response.LastRuleModification, 1707551387.0
        )

    @patch("requests.Session.post")
    def test_get_invalid_sampling_targets(self, mock_post=None):
        mock_post.return_value.configure_mock(
            **{
                "json.return_value": {
                    "LastRuleModification": None,
                    "SamplingTargetDocuments": None,
                    "UnprocessedStatistics": None,
                }
            }
        )
        client = _AwsXRaySamplingClient("http://127.0.0.1:2000")
        sampling_targets_response = client.get_sampling_targets(statistics=[])
        self.assertEqual(sampling_targets_response.SamplingTargetDocuments, [])
        self.assertEqual(sampling_targets_response.UnprocessedStatistics, [])
        self.assertEqual(sampling_targets_response.LastRuleModification, 0.0)
