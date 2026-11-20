# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from unittest import TestCase, mock

from kafka import KafkaConsumer, KafkaProducer
from wrapt import BoundFunctionWrapper

from opentelemetry import trace
from opentelemetry.instrumentation.kafka import KafkaInstrumentor
from opentelemetry.instrumentation.kafka.package import _instruments
from opentelemetry.trace import NoOpTracerProvider


class TestKafka(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = KafkaInstrumentor()

        instrumentation.instrument()
        self.assertTrue(isinstance(KafkaProducer.send, BoundFunctionWrapper))
        self.assertTrue(isinstance(KafkaConsumer.__next__, BoundFunctionWrapper))

        instrumentation.uninstrument()
        self.assertFalse(isinstance(KafkaProducer.send, BoundFunctionWrapper))
        self.assertFalse(isinstance(KafkaConsumer.__next__, BoundFunctionWrapper))

    def test_instrumentation_dependencies(self) -> None:
        instrumentation = KafkaInstrumentor()

        self.assertEqual(instrumentation.instrumentation_dependencies(), _instruments)

    def test_instrument_with_noop_tracer_provider(self) -> None:
        instrumentation = KafkaInstrumentor()
        provider = NoOpTracerProvider()
        produce_hook = mock.Mock()

        original_get_tracer = trace.get_tracer

        with (
            mock.patch.object(KafkaProducer, "send", autospec=True) as send_mock,
            mock.patch(
                "opentelemetry.instrumentation.kafka.trace.get_tracer",
                wraps=original_get_tracer,
            ) as get_tracer_mock,
        ):
            instrumentation.instrument(
                tracer_provider=provider,
                produce_hook=produce_hook,
            )

            try:
                producer = object.__new__(KafkaProducer)
                producer.config = {"bootstrap_servers": ["localhost:9092"]}

                result = producer.send("test_topic", b"test_message")

                send_mock.assert_called_once()
                self.assertIs(result, send_mock.return_value)

                self.assertIs(
                    get_tracer_mock.call_args.kwargs["tracer_provider"],
                    provider,
                )

                produce_hook.assert_called_once()
                span = produce_hook.call_args.args[0]
                self.assertFalse(span.is_recording())
                self.assertFalse(span.get_span_context().is_valid)
            finally:
                instrumentation.uninstrument()
