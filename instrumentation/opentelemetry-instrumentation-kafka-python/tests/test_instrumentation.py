# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from importlib.metadata import PackageNotFoundError
from unittest import TestCase
from unittest.mock import call, patch

from kafka import KafkaConsumer, KafkaProducer
from wrapt import BoundFunctionWrapper

from opentelemetry.instrumentation.kafka import KafkaInstrumentor
from opentelemetry.instrumentation.kafka.package import (
    _instruments_kafka_python,
    _instruments_kafka_python_ng,
)


class TestKafka(TestCase):
    def test_instrument_api(self) -> None:
        instrumentation = KafkaInstrumentor()

        instrumentation.instrument()
        self.assertTrue(isinstance(KafkaProducer.send, BoundFunctionWrapper))
        self.assertTrue(
            isinstance(KafkaConsumer.__next__, BoundFunctionWrapper)
        )

        instrumentation.uninstrument()
        self.assertFalse(isinstance(KafkaProducer.send, BoundFunctionWrapper))
        self.assertFalse(
            isinstance(KafkaConsumer.__next__, BoundFunctionWrapper)
        )

    @patch("opentelemetry.instrumentation.kafka.distribution")
    def test_instrumentation_dependencies_kafka_python_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = KafkaInstrumentor()

        def _distribution(name):
            if name == "kafka-python":
                return None
            raise PackageNotFoundError

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 2)
        self.assertEqual(
            mock_distribution.mock_calls,
            [
                call("kafka-python-ng"),
                call("kafka-python"),
            ],
        )
        self.assertEqual(package_to_instrument, (_instruments_kafka_python,))

    @patch("opentelemetry.instrumentation.kafka.distribution")
    def test_instrumentation_dependencies_kafka_python_ng_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = KafkaInstrumentor()

        def _distribution(name):
            if name == "kafka-python-ng":
                return None
            raise PackageNotFoundError

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 1)
        self.assertEqual(
            mock_distribution.mock_calls, [call("kafka-python-ng")]
        )
        self.assertEqual(
            package_to_instrument, (_instruments_kafka_python_ng,)
        )

    @patch("opentelemetry.instrumentation.kafka.distribution")
    def test_instrumentation_dependencies_both_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = KafkaInstrumentor()

        def _distribution(name):
            # The function returns None here for all names
            # to simulate both packages being installed
            return None

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 1)
        self.assertEqual(
            mock_distribution.mock_calls, [call("kafka-python-ng")]
        )
        self.assertEqual(
            package_to_instrument, (_instruments_kafka_python_ng,)
        )

    @patch("opentelemetry.instrumentation.kafka.distribution")
    def test_instrumentation_dependencies_none_installed(
        self, mock_distribution
    ) -> None:
        instrumentation = KafkaInstrumentor()

        def _distribution(name):
            # Function raises PackageNotFoundError
            # if name is not in the list. We will
            # raise it for both names to simulate
            # neither being installed
            raise PackageNotFoundError

        mock_distribution.side_effect = _distribution
        package_to_instrument = instrumentation.instrumentation_dependencies()

        self.assertEqual(mock_distribution.call_count, 2)
        self.assertEqual(
            mock_distribution.mock_calls,
            [
                call("kafka-python-ng"),
                call("kafka-python"),
            ],
        )
        self.assertEqual(
            package_to_instrument,
            (_instruments_kafka_python, _instruments_kafka_python_ng),
        )
