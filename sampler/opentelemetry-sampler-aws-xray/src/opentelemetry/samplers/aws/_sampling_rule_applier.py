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

from typing import Optional

from opentelemetry.samplers.aws._clock import _Clock
from opentelemetry.samplers.aws._sampling_rule import _SamplingRule
from opentelemetry.samplers.aws._sampling_statistics_document import (
    _SamplingStatisticsDocument,
)
from opentelemetry.samplers.aws._sampling_target import _SamplingTarget


class _SamplingRuleApplier:
    def __init__(
        self,
        sampling_rule: _SamplingRule,
        client_id: str,
        clock: _Clock,
        statistics: Optional[_SamplingStatisticsDocument] = None,
        target: Optional[_SamplingTarget] = None,
    ):
        self.__client_id = client_id
        self._clock = clock
        self.sampling_rule = sampling_rule

        # (TODO) Just store Sampling Rules for now, rest of implementation for later
