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

from decimal import Decimal
from threading import Lock

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock


class _RateLimiter:  # pyright: ignore[reportUnusedClass]
    def __init__(self, max_balance_in_seconds: int, quota: int, clock: _Clock):
        # max_balance_in_seconds is usually 1
        # pylint: disable=invalid-name
        self.MAX_BALANCE_MILLIS = Decimal(max_balance_in_seconds * 1000.0)
        self._clock = clock

        self._quota = Decimal(quota)
        self.__wallet_floor_millis = Decimal(
            self._clock.now().timestamp() * 1000.0
        )
        # current "wallet_balance" would be ceiling - floor

        self.__lock = Lock()

    def try_spend(self, cost: float) -> bool:
        if self._quota == 0:
            return False

        quota_per_millis = self._quota / Decimal(1000.0)

        # assume divide by zero not possible
        cost_in_millis = Decimal(cost) / quota_per_millis

        with self.__lock:
            wallet_ceiling_millis = Decimal(
                self._clock.now().timestamp() * 1000.0
            )
            current_balance_millis = (
                wallet_ceiling_millis - self.__wallet_floor_millis
            )
            current_balance_millis = min(
                current_balance_millis, self.MAX_BALANCE_MILLIS
            )
            pending_remaining_balance_millis = (
                current_balance_millis - cost_in_millis
            )
            if pending_remaining_balance_millis >= 0:
                self.__wallet_floor_millis = (
                    wallet_ceiling_millis - pending_remaining_balance_millis
                )
                return True
            # No changes to the wallet state
            return False
