# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Includes work from:
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from unittest import TestCase

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace.sampler._clock import _Clock


class TestClock(TestCase):
    def test_from_timestamp(self):
        pass

    def test_time_delta(self):
        clock = _Clock()
        dt = clock.from_timestamp(1707551387.0)
        delta = clock.time_delta(3600)
        new_dt = dt + delta
        self.assertTrue(new_dt.timestamp() - dt.timestamp() == 3600)
