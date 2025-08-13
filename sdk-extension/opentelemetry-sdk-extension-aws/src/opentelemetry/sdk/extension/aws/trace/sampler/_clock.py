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


class _Clock:
    def __init__(self):
        self.__datetime = datetime.datetime

    def now(self) -> datetime.datetime:
        return self.__datetime.now()

    # pylint: disable=no-self-use
    def from_timestamp(self, timestamp: float) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(timestamp)

    def time_delta(self, seconds: float) -> datetime.timedelta:
        return datetime.timedelta(seconds=seconds)

    def max(self) -> datetime.datetime:
        return datetime.datetime.max
