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


from confluent_kafka import Producer, Consumer

from kafka_instrumentation import ConfluentKafkaInstrumentor, ProxiedProducer, ProxiedConsumer


class TestConfluentKafka(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = ConfluentKafkaInstrumentor()

        p = Producer({'bootstrap.servers': 'localhost:29092'})
        p = instrumentation.instrument_producer(p)

        self.assertEqual(p.__class__, ProxiedProducer)

        p = instrumentation.uninstrument_producer(p)
        self.assertEqual(p.__class__, Producer)

        p = Producer({'bootstrap.servers': 'localhost:29092'})
        p = instrumentation.instrument_producer(p)

        self.assertEqual(p.__class__, ProxiedProducer)

        p = instrumentation.uninstrument_producer(p)
        self.assertEqual(p.__class__, Producer)

        c = Consumer({
            'bootstrap.servers': 'localhost:29092',
            'group.id': 'mygroup',
            'auto.offset.reset': 'earliest'
        })

        c = instrumentation.instrument_consumer(c)
        self.assertEqual(c.__class__, ProxiedConsumer)

        c = instrumentation.uninstrument_consumer(c)
        self.assertEqual(c.__class__, Consumer)

