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

from logging import getLogger
from typing import Optional, List

_logger = getLogger(__name__)


# Disable snake_case naming style so this class can match the sampling rules response from X-Ray
# pylint: disable=invalid-name
class _SamplingTarget:
    def __init__(
        self,
        FixedRate: Optional[float] = None,
        Interval: Optional[int] = None,
        ReservoirQuota: Optional[int] = None,
        ReservoirQuotaTTL: Optional[float] = None,
        RuleName: Optional[str] = None,
    ):
        self.FixedRate = FixedRate if FixedRate is not None else 0.0
        self.Interval = Interval  # can be None
        self.ReservoirQuota = ReservoirQuota  # can be None
        self.ReservoirQuotaTTL = ReservoirQuotaTTL  # can be None
        self.RuleName = RuleName if RuleName is not None else ""


class _UnprocessedStatistics:
    def __init__(
        self,
        ErrorCode: Optional[str] = None,
        Message: Optional[str] = None,
        RuleName: Optional[str] = None,
    ):
        self.ErrorCode = ErrorCode if ErrorCode is not None else ""
        self.Message = Message if ErrorCode is not None else ""
        self.RuleName = RuleName if ErrorCode is not None else ""


class _SamplingTargetResponse:
    def __init__(
        self,
        LastRuleModification: Optional[float],
        SamplingTargetDocuments: Optional[List[_SamplingTarget]] = None,
        UnprocessedStatistics: Optional[List[_UnprocessedStatistics]] = None,
    ):
        self.LastRuleModification: float = LastRuleModification if LastRuleModification is not None else 0.0

        self.SamplingTargetDocuments: List[_SamplingTarget] = []
        if SamplingTargetDocuments is not None:
            for document in SamplingTargetDocuments:
                try:
                    self.SamplingTargetDocuments.append(_SamplingTarget(**document))
                except TypeError as e:
                    _logger.debug("TypeError occurred: %s", e)

        self.UnprocessedStatistics: List[_UnprocessedStatistics] = []
        if UnprocessedStatistics is not None:
            for unprocessed in UnprocessedStatistics:
                try:
                    self.UnprocessedStatistics.append(_UnprocessedStatistics(**unprocessed))
                except TypeError as e:
                    _logger.debug("TypeError occurred: %s", e)
