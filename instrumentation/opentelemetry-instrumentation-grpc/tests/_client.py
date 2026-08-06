# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from .protobuf.test_server_pb2 import Request

CLIENT_ID = 1


def simple_method(stub, error=False):
    request = Request(
        client_id=CLIENT_ID, request_data="error" if error else "data"
    )
    stub.SimpleMethod(request, metadata=(("key", "value"),))


def simple_method_future(stub, error=False):
    request = Request(
        client_id=CLIENT_ID, request_data="error" if error else "data"
    )
    return stub.SimpleMethod.future(request, metadata=(("key", "value"),))


def client_streaming_method(stub, error=False):
    # create a generator
    def request_messages():
        for _ in range(5):
            request = Request(
                client_id=CLIENT_ID, request_data="error" if error else "data"
            )
            yield request

    stub.ClientStreamingMethod(
        request_messages(), metadata=(("key", "value"),)
    )


def server_streaming_method(stub, error=False):
    request = Request(
        client_id=CLIENT_ID, request_data="error" if error else "data"
    )
    response_iterator = stub.ServerStreamingMethod(
        request, metadata=(("key", "value"),)
    )
    list(response_iterator)


def bidirectional_streaming_method(stub, error=False):
    def request_messages():
        for _ in range(5):
            request = Request(
                client_id=CLIENT_ID, request_data="error" if error else "data"
            )
            yield request

    response_iterator = stub.BidirectionalStreamingMethod(
        request_messages(), metadata=(("key", "value"),)
    )

    list(response_iterator)
