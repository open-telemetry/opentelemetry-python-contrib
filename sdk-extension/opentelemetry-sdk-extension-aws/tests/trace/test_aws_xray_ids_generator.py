# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import datetime
import time
import unittest

# pylint: disable=no-name-in-module
from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator
from opentelemetry.trace.span import INVALID_TRACE_ID


class AwsXRayIdGeneratorTest(unittest.TestCase):
    def test_ids_are_valid(self):
        id_generator = AwsXRayIdGenerator()
        for _ in range(1000):
            trace_id = id_generator.generate_trace_id()
            self.assertTrue(trace_id != INVALID_TRACE_ID)
            span_id = id_generator.generate_span_id()
            self.assertTrue(span_id != INVALID_TRACE_ID)

    def test_id_timestamps_are_acceptable_for_xray(self):
        id_generator = AwsXRayIdGenerator()
        for _ in range(1000):
            trace_id = id_generator.generate_trace_id()
            trace_id_time = trace_id >> 96
            current_time = int(time.time())
            self.assertLessEqual(trace_id_time, current_time)
            one_month_ago_time = int(
                (datetime.datetime.now() - datetime.timedelta(30)).timestamp()
            )
            self.assertGreater(trace_id_time, one_month_ago_time)
