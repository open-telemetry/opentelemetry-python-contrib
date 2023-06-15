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
from unittest import TestCase

from karapace.kafka_rest_apis import UserRestProxy
from wrapt import BoundFunctionWrapper

from opentelemetry.instrumentation.karapace import KarapaceInstrumentor


class TestKafka(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = KarapaceInstrumentor()

        instrumentation.instrument()
        self.assertTrue(isinstance(UserRestProxy.publish, BoundFunctionWrapper))

        instrumentation.uninstrument()
        self.assertFalse(isinstance(UserRestProxy.pulish, BoundFunctionWrapper))
