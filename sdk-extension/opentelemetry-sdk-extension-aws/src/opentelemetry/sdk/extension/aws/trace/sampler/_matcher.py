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

from __future__ import annotations

import re

from opentelemetry.semconv._incubating.attributes.cloud_attributes import (
    CloudPlatformValues,
)
from opentelemetry.util.types import Attributes, AttributeValue

cloud_platform_mapping = {
    CloudPlatformValues.AWS_LAMBDA.value: "AWS::Lambda::Function",
    CloudPlatformValues.AWS_ELASTIC_BEANSTALK.value: "AWS::ElasticBeanstalk::Environment",
    CloudPlatformValues.AWS_EC2.value: "AWS::EC2::Instance",
    CloudPlatformValues.AWS_ECS.value: "AWS::ECS::Container",
    CloudPlatformValues.AWS_EKS.value: "AWS::EKS::Container",
}


class _Matcher:
    @staticmethod
    def wild_card_match(
        text: AttributeValue | None = None, pattern: str | None = None
    ) -> bool:
        if pattern == "*":
            return True
        if not isinstance(text, str) or pattern is None:
            return False
        if len(pattern) == 0:
            return len(text) == 0
        for char in pattern:
            if char in ("*", "?"):
                return (
                    re.fullmatch(_Matcher.to_regex_pattern(pattern), text)
                    is not None
                )
        return pattern == text

    @staticmethod
    def to_regex_pattern(rule_pattern: str) -> str:
        token_start = -1
        regex_pattern = ""
        for index, char in enumerate(rule_pattern):
            char = rule_pattern[index]
            if char in ("*", "?"):
                if token_start != -1:
                    regex_pattern += re.escape(rule_pattern[token_start:index])
                    token_start = -1
                if char == "*":
                    regex_pattern += ".*"
                else:
                    regex_pattern += "."
            else:
                if token_start == -1:
                    token_start = index
        if token_start != -1:
            regex_pattern += re.escape(rule_pattern[token_start:])
        return regex_pattern

    @staticmethod
    def attribute_match(
        attributes: Attributes | None = None,
        rule_attributes: dict[str, str] | None = None,
    ) -> bool:
        if rule_attributes is None or len(rule_attributes) == 0:
            return True
        if (
            attributes is None
            or len(attributes) == 0
            or len(rule_attributes) > len(attributes)
        ):
            return False

        matched_count = 0
        for key, val in attributes.items():
            text_to_match = val
            pattern = rule_attributes.get(key, None)
            if pattern is None:
                continue
            if _Matcher.wild_card_match(text_to_match, pattern):
                matched_count += 1
        return matched_count == len(rule_attributes)
