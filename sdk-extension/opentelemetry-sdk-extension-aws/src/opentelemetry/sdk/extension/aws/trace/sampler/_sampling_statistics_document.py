# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock


# Disable snake_case naming style so this class can match the statistics document response from X-Ray
# pylint: disable=invalid-name
class _SamplingStatisticsDocument:  # pyright: ignore[reportUnusedClass]
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
