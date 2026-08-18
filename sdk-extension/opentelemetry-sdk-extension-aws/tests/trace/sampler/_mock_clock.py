# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import datetime

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock


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
