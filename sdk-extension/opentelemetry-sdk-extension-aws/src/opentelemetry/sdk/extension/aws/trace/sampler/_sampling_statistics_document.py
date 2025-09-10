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

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock


# Disable snake_case naming style so this class can match the statistics document response from X-Ray
# pylint: disable=invalid-name
class _SamplingStatisticsDocument:
    def __init__(
        self,
        clientID: str,
        ruleName: str,
        RequestCount: int = 0,
        BorrowCount: int = 0,
        SampleCount: int = 0,
    ):
        self.ClientID = clientID
        self.RuleName = ruleName
        self.Timestamp = None

        self.RequestCount = RequestCount
        self.BorrowCount = BorrowCount
        self.SampleCount = SampleCount

    def snapshot(self, clock: _Clock):
        return {
            "ClientID": self.ClientID,
            "RuleName": self.RuleName,
            "Timestamp": clock.now().timestamp(),
            "RequestCount": self.RequestCount,
            "BorrowCount": self.BorrowCount,
            "SampleCount": self.SampleCount,
        }
