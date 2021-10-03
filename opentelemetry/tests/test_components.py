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

import unittest

from opentelemetry.conf import components


class TestComponents(unittest.TestCase):
    # pylint: disable=protected-access

    def test_defaults(self):
        self.assertEqual(components._DEFAULT_ID_GENERATOR, "random")
        self.assertEqual(
            components._DEFAULT_SPAN_EXPORTER, "otlp_proto_grpc_span"
        )
