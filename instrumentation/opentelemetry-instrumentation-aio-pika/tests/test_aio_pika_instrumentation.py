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
from unittest import TestCase, mock

import wrapt
from aio_pika import Exchange, Queue

from opentelemetry.instrumentation.aio_pika import AioPikaInstrumentor
from opentelemetry.instrumentation.aio_pika.package import (
    _instrumentation_name,
)


class TestPika(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = AioPikaInstrumentor()
        instrumentation.instrument()
        self.assertTrue(isinstance(Queue.consume, wrapt.BoundFunctionWrapper))
        self.assertTrue(
            isinstance(Exchange.publish, wrapt.BoundFunctionWrapper)
        )
        instrumentation.uninstrument()
        self.assertFalse(isinstance(Queue.consume, wrapt.BoundFunctionWrapper))
        self.assertFalse(
            isinstance(Exchange.publish, wrapt.BoundFunctionWrapper)
        )

    def test_instrumentation_name(self) -> None:
        with mock.patch("opentelemetry.trace.get_tracer") as mock_get_tracer:
            instrumentation = AioPikaInstrumentor()
            instrumentation.instrument()
            mock_get_tracer.assert_called_once()
            self.assertEqual(
                mock_get_tracer.call_args[0][0], _instrumentation_name
            )
            instrumentation.uninstrument()
