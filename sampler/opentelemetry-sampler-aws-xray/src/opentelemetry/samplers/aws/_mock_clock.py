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

import datetime

from opentelemetry.samplers.aws._clock import _Clock


class MockClock(_Clock):
    def __init__(self, dt: datetime.datetime = datetime.datetime.now()):
        self.time_now = dt
        super()

    def now(self) -> datetime.datetime:
        return self.time_now

    def add_time(self, seconds: float) -> None:
        self.time_now += self.time_delta(seconds)

    def set_time(self, dt: datetime.datetime) -> None:
        self.time_now = dt
