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

import datetime
import json
import os
from unittest import TestCase
from unittest.mock import patch

from opentelemetry.samplers.aws._mock_clock import MockClock

from opentelemetry.samplers.aws._clock import _Clock
from opentelemetry.samplers.aws._sampling_rule import _SamplingRule
from opentelemetry.samplers.aws._sampling_rule_applier import _SamplingRuleApplier
from opentelemetry.samplers.aws._sampling_target import _SamplingTarget
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.sampling import Decision, SamplingResult, TraceIdRatioBased
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.util.types import Attributes

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TEST_DIR, "data")

CLIENT_ID = "12345678901234567890abcd"


# pylint: disable=no-member
class TestSamplingRuleApplier(TestCase):
    pass