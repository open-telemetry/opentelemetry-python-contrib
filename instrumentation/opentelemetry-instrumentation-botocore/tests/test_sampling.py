# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import asyncio
from collections.abc import Callable
from contextlib import AsyncExitStack, closing
from importlib import import_module
from typing import Any

import botocore.session
import pytest
from botocore.stub import Stubber

from opentelemetry.instrumentation.botocore import AiobotocoreInstrumentor, BotocoreInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.semconv._incubating.attributes import messaging_attributes
from opentelemetry.semconv._incubating.attributes.cloud_attributes import CLOUD_REGION
from opentelemetry.semconv._incubating.attributes.rpc_attributes import RPC_METHOD, RPC_SERVICE, RPC_SYSTEM
from opentelemetry.semconv.attributes.server_attributes import SERVER_ADDRESS, SERVER_PORT
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.samplertestutil import CapturingSampler
from opentelemetry.util.types import AttributeValue

_RESPONSE_METADATA = {"RequestId": "request-1", "HTTPStatusCode": 200, "RetryAttempts": 0}


@pytest.fixture(params=[False, True], ids=["botocore", "aiobotocore"])
def call_aws(
    request: pytest.FixtureRequest, span_exporter: InMemorySpanExporter, logger_provider: Any, meter_provider: Any
) -> Callable:
    is_async = request.param
    if is_async:
        pytest.importorskip("aiobotocore")
    instrumentor = AiobotocoreInstrumentor() if is_async else BotocoreInstrumentor()
    request.addfinalizer(instrumentor.uninstrument)

    def call(
        sampler: CapturingSampler,
        service: str,
        operation: str,
        params: dict[str, Any],
        response: dict[str, Any],
    ) -> Any:
        provider = TracerProvider(sampler=sampler)
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
        request.addfinalizer(provider.shutdown)
        instrumentor.instrument(
            tracer_provider=provider, logger_provider=logger_provider, meter_provider=meter_provider
        )
        session_module = import_module("aiobotocore.session") if is_async else botocore.session
        session = session_module.get_session()
        session.set_credentials(access_key="access-key", secret_key="secret-key")

        async def invoke() -> Any:
            async with AsyncExitStack() as stack:
                client_manager = session.create_client(service, region_name="us-west-2")
                client = (
                    await stack.enter_async_context(client_manager)
                    if is_async
                    else stack.enter_context(closing(client_manager))
                )
                stubber = Stubber(client)
                stubber.add_response(operation, response, params)
                stack.enter_context(stubber)
                result = getattr(client, operation)(**params)
                return await result if is_async else result

        return asyncio.run(invoke())

    return call


def _base_attributes(service: str, operation: str) -> dict[str, AttributeValue]:
    return {
        RPC_SYSTEM: "aws-api",
        RPC_SERVICE: service,
        RPC_METHOD: operation,
        CLOUD_REGION: "us-west-2",
        SERVER_ADDRESS: f"{service.lower()}.us-west-2.amazonaws.com",
        SERVER_PORT: 443,
    }


def _assert_attributes(sampler: CapturingSampler, expected: dict[str, AttributeValue]) -> None:
    assert sampler.attributes == expected
    for key, value in expected.items():
        assert type(sampler.attributes[key]) is type(value)


def test_sqs_attributes_passed_to_sampler(call_aws: Callable, span_exporter: InMemorySpanExporter) -> None:
    sampler = CapturingSampler()
    queue_url = "https://sqs.us-west-2.amazonaws.com/123456789012/queue-1"
    response = {"MessageId": "message-1", "ResponseMetadata": _RESPONSE_METADATA}

    assert (
        call_aws(sampler, "sqs", "send_message", {"QueueUrl": queue_url, "MessageBody": "hello"}, response) == response
    )

    _assert_attributes(
        sampler,
        {
            **_base_attributes("SQS", "SendMessage"),
            "aws.queue_url": queue_url,
            messaging_attributes.MESSAGING_SYSTEM: "aws.sqs",
            SpanAttributes.MESSAGING_URL: queue_url,
            SpanAttributes.MESSAGING_DESTINATION: "queue-1",
        },
    )
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].attributes[messaging_attributes.MESSAGING_MESSAGE_ID] == "message-1"
    assert messaging_attributes.MESSAGING_MESSAGE_ID not in sampler.attributes
