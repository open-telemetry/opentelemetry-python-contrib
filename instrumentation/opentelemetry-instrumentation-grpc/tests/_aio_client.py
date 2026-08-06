# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from .protobuf.test_server_pb2 import Request

CLIENT_ID = 1


async def simple_method(stub, error=False):
    request = Request(
        client_id=CLIENT_ID, request_data="error" if error else "data"
    )
    return await stub.SimpleMethod(request, metadata=(("key", "value"),))


async def client_streaming_method(stub, error=False):
    # create a generator
    def request_messages():
        for _ in range(5):
            request = Request(
                client_id=CLIENT_ID, request_data="error" if error else "data"
            )
            yield request

    return await stub.ClientStreamingMethod(request_messages())


def server_streaming_method(stub, error=False):
    request = Request(
        client_id=CLIENT_ID, request_data="error" if error else "data"
    )

    return stub.ServerStreamingMethod(request, metadata=(("key", "value"),))


def bidirectional_streaming_method(stub, error=False):
    # create a generator
    def request_messages():
        for _ in range(5):
            request = Request(
                client_id=CLIENT_ID, request_data="error" if error else "data"
            )
            yield request

    return stub.BidirectionalStreamingMethod(
        request_messages(), metadata=(("key", "value"),)
    )
