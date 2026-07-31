# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import datetime


class _Clock:  # pyright: ignore[reportUnusedClass]
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
