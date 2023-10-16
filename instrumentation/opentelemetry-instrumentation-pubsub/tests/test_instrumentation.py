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

from wrapt import BoundFunctionWrapper

from google.cloud.pubsub_v1 import PublisherClient, SubscriberClient

from opentelemetry.instrumentation.pubsub import PubsubInstrumentor


class TestKafka(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = PubsubInstrumentor()

        instrumentation.instrument()
        self.assertTrue(isinstance(PublisherClient.publish, BoundFunctionWrapper))
        self.assertTrue(
            isinstance(SubscriberClient.subscribe, BoundFunctionWrapper)
        )

        instrumentation.uninstrument()
        self.assertFalse(isinstance(PublisherClient.publish, BoundFunctionWrapper))
        self.assertFalse(
            isinstance(SubscriberClient.subscribe, BoundFunctionWrapper)
        )
