# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from logging import getLogger
from typing import Any, List, cast

_logger = getLogger(__name__)


# Disable snake_case naming style so this class can match the sampling rules response from X-Ray
# pylint: disable=invalid-name
class _SamplingTarget:
    def __init__(
        self,
        FixedRate: float | None = None,
        Interval: int | None = None,
        ReservoirQuota: int | None = None,
        ReservoirQuotaTTL: float | None = None,
        RuleName: str | None = None,
    ):
        self.FixedRate = FixedRate if FixedRate is not None else 0.0
        self.Interval = Interval  # can be None
        self.ReservoirQuota = ReservoirQuota  # can be None
        self.ReservoirQuotaTTL = ReservoirQuotaTTL  # can be None
        self.RuleName = RuleName if RuleName is not None else ""


class _UnprocessedStatistics:
    def __init__(
        self,
        ErrorCode: str | None = None,
        Message: str | None = None,
        RuleName: str | None = None,
    ):
        self.ErrorCode = ErrorCode if ErrorCode is not None else ""
        self.Message = Message if ErrorCode is not None else ""
        self.RuleName = RuleName if ErrorCode is not None else ""


class _SamplingTargetResponse:  # pyright: ignore[reportUnusedClass]
    def __init__(
        self,
        LastRuleModification: float | None,
        SamplingTargetDocuments: List[_SamplingTarget] | None = None,
        UnprocessedStatistics: List[_UnprocessedStatistics] | None = None,
    ):
        self.LastRuleModification: float = (
            LastRuleModification if LastRuleModification is not None else 0.0
        )

        self.SamplingTargetDocuments: List[_SamplingTarget] = []
        if SamplingTargetDocuments is not None:
            for document in SamplingTargetDocuments:
                try:
                    self.SamplingTargetDocuments.append(
                        _SamplingTarget(**cast(Any, document))
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught
                    _logger.debug("Error creating _SamplingTarget: %s", e)

        self.UnprocessedStatistics: List[_UnprocessedStatistics] = []
        if UnprocessedStatistics is not None:
            for unprocessed in UnprocessedStatistics:
                try:
                    self.UnprocessedStatistics.append(
                        _UnprocessedStatistics(**cast(Any, unprocessed))
                    )
                except Exception as e:  # pylint: disable=broad-exception-caught
                    _logger.debug(
                        "Error creating _UnprocessedStatistics: %s", e
                    )
