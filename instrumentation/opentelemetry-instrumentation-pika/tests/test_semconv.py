# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest import mock

import pytest
from pika.adapters.blocking_connection import (
    BlockingChannel,
    _ConsumerDeliveryEvt,
    _QueueConsumerGeneratorInfo,
)
from pika.channel import Channel
from pika.spec import Basic, BasicProperties

from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
    _StabilityMode,
)
from opentelemetry.instrumentation.environment_variables import OTEL_SEMCONV_STABILITY_OPT_IN
from opentelemetry.instrumentation.pika import PikaInstrumentor, utils
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from opentelemetry.util.types import AttributeValue


@pytest.fixture(params=[_StabilityMode.DEFAULT, _StabilityMode.MESSAGING, _StabilityMode.MESSAGING_DUP])
def mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> _StabilityMode:
    selected: _StabilityMode = request.param
    monkeypatch.setenv(OTEL_SEMCONV_STABILITY_OPT_IN, selected.value)
    monkeypatch.setattr(_OpenTelemetrySemanticConventionStability, "_initialized", False)
    monkeypatch.setattr(_OpenTelemetrySemanticConventionStability, "_OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING", {})
    return selected


@pytest.fixture
def telemetry() -> Iterator[tuple[TracerProvider, InMemorySpanExporter]]:
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield provider, exporter
    provider.shutdown()


def assert_span(
    span: ReadableSpan,
    mode: _StabilityMode,
    legacy_destination: str,
    destination: str,
    operation: str,
    *,
    has_connection: bool = True,
    include_ids: bool = True,
) -> None:
    expected: dict[str, AttributeValue] = {"messaging.system": "rabbitmq"}
    if include_ids:
        expected["messaging.message.id"] = "message-1"
    if mode != _StabilityMode.MESSAGING:
        expected["messaging.destination"] = legacy_destination
        if operation == "publish":
            expected["messaging.temp_destination"] = True
        else:
            expected["messaging.operation"] = "receive"
        if include_ids:
            expected["messaging.conversation_id"] = "conversation-1"
        if has_connection:
            expected.update({"net.peer.name": "localhost", "net.peer.port": 5672})
    if mode != _StabilityMode.DEFAULT:
        expected.update(
            {
                "messaging.destination.name": destination,
                "messaging.operation.name": operation,
                "messaging.operation.type": "send" if operation == "publish" else operation,
            }
        )
        if include_ids:
            expected["messaging.message.conversation_id"] = "conversation-1"
        if has_connection:
            expected.update({"server.address": "localhost", "server.port": 5672})

    assert dict(span.attributes) == expected
    for key, value in expected.items():
        assert type(span.attributes[key]) is type(value)
    legacy_operation = "send" if operation == "publish" else "receive"
    expected_name = (
        f"{legacy_destination} {legacy_operation}" if mode == _StabilityMode.DEFAULT else f"{operation} {destination}"
    )
    assert span.name == expected_name
    assert span.instrumentation_scope.schema_url == (
        "https://opentelemetry.io/schemas/1.11.0"
        if mode == _StabilityMode.DEFAULT
        else "https://opentelemetry.io/schemas/1.44.0"
    )


@pytest.mark.parametrize("channel_type", [BlockingChannel, Channel])
@pytest.mark.parametrize(
    ("exchange", "routing_key", "destination"),
    [
        ("events", "orders", "events:orders"),
        ("events", "", "events"),
        ("", "orders", "orders"),
        ("", "", "amq.default"),
    ],
)
@pytest.mark.parametrize("include_ids", [True, False])
def test_publish_semconv(
    mode: _StabilityMode,
    telemetry: tuple[TracerProvider, InMemorySpanExporter],
    channel_type: type[BlockingChannel | Channel],
    exchange: str,
    routing_key: str,
    destination: str,
    include_ids: bool,
) -> None:
    # Arrange
    provider, exporter = telemetry
    channel = mock.MagicMock(spec=channel_type)
    channel._consumer_infos = {}
    channel._consumers = {}
    params = SimpleNamespace(host="localhost", port=5672)
    channel.connection = (
        SimpleNamespace(_impl=SimpleNamespace(params=params))
        if channel_type is BlockingChannel
        else SimpleNamespace(params=params)
    )
    original = channel.basic_publish
    properties = BasicProperties(
        message_id="message-1" if include_ids else None,
        correlation_id="conversation-1" if include_ids else None,
    )
    PikaInstrumentor.instrument_channel(channel, tracer_provider=provider)

    # Act: once instrumented, sending must not resolve the mode again.
    with mock.patch.object(_OpenTelemetrySemanticConventionStability, "_initialize", side_effect=AssertionError):
        result = channel.basic_publish(exchange, routing_key, b"hello", properties)

    # Assert
    assert result is original.return_value
    original.assert_called_once_with(exchange, routing_key, b"hello", properties, False)
    assert "traceparent" in properties.headers
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].kind == SpanKind.PRODUCER
    assert_span(spans[0], mode, exchange or routing_key, destination, "publish", include_ids=include_ids)


@pytest.mark.parametrize("channel_type", [BlockingChannel, Channel])
@pytest.mark.parametrize("register_after_setup", [True, False])
def test_callback_semconv(
    mode: _StabilityMode,
    telemetry: tuple[TracerProvider, InMemorySpanExporter],
    channel_type: type[BlockingChannel | Channel],
    register_after_setup: bool,
) -> None:
    # Arrange
    provider, exporter = telemetry
    channel = mock.MagicMock(spec=channel_type)
    channel.connection = SimpleNamespace(params=SimpleNamespace(host="localhost", port=5672))
    callback = mock.Mock(spec=[])
    callback_attr = PikaInstrumentor.CONSUMER_CALLBACK_ATTR
    consumer_info = SimpleNamespace(**{callback_attr: callback})
    consumers = {} if register_after_setup else {"tag": consumer_info}
    channel._consumer_infos = consumers
    channel._consumers = consumers
    PikaInstrumentor.instrument_channel(channel, tracer_provider=provider)
    method = Basic.Deliver(exchange="events", routing_key="orders")
    properties = BasicProperties(message_id="message-1", correlation_id="conversation-1")

    # Act
    with mock.patch.object(_OpenTelemetrySemanticConventionStability, "_initialize", side_effect=AssertionError):
        if register_after_setup:
            consumers["tag"] = consumer_info
            channel.basic_consume("orders", callback)
        result = getattr(consumer_info, callback_attr)(channel, method, properties, b"hello")

    # Assert
    assert result is callback.return_value
    callback.assert_called_once_with(channel, method, properties, b"hello")
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].kind == SpanKind.CONSUMER
    assert_span(spans[0], mode, "events", "events:orders", "process")


@pytest.mark.parametrize(
    ("exchange", "routing_key", "destination"),
    [
        ("events", "orders", "events:orders"),
        ("events", "", "events"),
        ("", "orders", "orders"),
        ("", "", "amq.default"),
    ],
)
def test_generator_semconv(
    mode: _StabilityMode,
    telemetry: tuple[TracerProvider, InMemorySpanExporter],
    exchange: str,
    routing_key: str,
    destination: str,
) -> None:
    # Arrange: exercise the global setup path and its separate tracer.
    provider, exporter = telemetry
    instrumentor = PikaInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        generator = _QueueConsumerGeneratorInfo(params=("orders", False, False), consumer_tag="tag")
        event = _ConsumerDeliveryEvt(
            Basic.Deliver(exchange=exchange, routing_key=routing_key),
            BasicProperties(message_id="message-1", correlation_id="conversation-1"),
            b"hello",
        )
        generator.pending_events.append(event)

        # Act
        with mock.patch.object(_OpenTelemetrySemanticConventionStability, "_initialize", side_effect=AssertionError):
            result = generator.pending_events.popleft()
            # This also detaches the context installed by the first popleft.
            with pytest.raises(IndexError):
                generator.pending_events.popleft()

        # Assert
        assert result is event
        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].kind == (SpanKind.CONSUMER if mode == _StabilityMode.DEFAULT else SpanKind.CLIENT)
        assert_span(spans[0], mode, exchange or routing_key, destination, "receive", has_connection=False)
    finally:
        instrumentor.uninstrument()


@pytest.mark.parametrize("publish", [True, False])
def test_wrappers_preserve_library_exception(
    mode: _StabilityMode,
    telemetry: tuple[TracerProvider, InMemorySpanExporter],
    publish: bool,
) -> None:
    # Arrange
    provider, exporter = telemetry
    tracer = provider.get_tracer(__name__)
    error = RuntimeError("underlying operation failed")
    original = mock.Mock(side_effect=error)
    channel = mock.MagicMock(spec=Channel)
    channel.connection = SimpleNamespace(params=SimpleNamespace(host="localhost", port=5672))
    properties = BasicProperties()

    # Act
    with pytest.raises(RuntimeError) as raised:
        if publish:
            wrapped = utils._decorate_basic_publish(original, channel, tracer, sem_conv_opt_in_mode=mode)
            wrapped("events", "orders", b"hello", properties)
        else:
            wrapped = utils._decorate_callback(original, tracer, "tag", sem_conv_opt_in_mode=mode)
            wrapped(channel, Basic.Deliver(exchange="events", routing_key="orders"), properties, b"hello")

    # Assert
    assert raised.value is error
    assert len(exporter.get_finished_spans()) == 1
    assert exporter.get_finished_spans()[0].status.is_ok is False
