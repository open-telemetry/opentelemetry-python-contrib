# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_rule import (
    _SamplingRule,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_statistics_document import (
    _SamplingStatisticsDocument,
)
from opentelemetry.sdk.extension.aws.trace.sampler._sampling_target import (
    _SamplingTarget,
)


class _SamplingRuleApplier:
    def __init__(
        self,
        sampling_rule: _SamplingRule,
        client_id: str,
        clock: _Clock,
        statistics: _SamplingStatisticsDocument | None = None,
        target: _SamplingTarget | None = None,
    ):
        self.__client_id = client_id  # pylint: disable=W0238
        self._clock = clock
        self.sampling_rule = sampling_rule

        # (TODO) Just store Sampling Rules for now, rest of implementation for later
