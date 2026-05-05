# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os
from unittest import TestCase

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TEST_DIR, "data")

CLIENT_ID = "12345678901234567890abcd"


# pylint: disable=no-member
class TestSamplingRuleApplier(TestCase):
    pass
