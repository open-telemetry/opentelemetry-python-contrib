# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from concurrent import futures

import grpc

from .protobuf import test_server_pb2, test_server_pb2_grpc

SERVER_ID = 1


class TestServer(test_server_pb2_grpc.GRPCTestServerServicer):
    # pylint: disable=invalid-name
    # pylint: disable=no-self-use

    def SimpleMethod(self, request, context):
        if request.request_data == "error":
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            return test_server_pb2.Response()
        response = test_server_pb2.Response(
            server_id=SERVER_ID, response_data="data"
        )
        return response

    def ClientStreamingMethod(self, request_iterator, context):
        data = list(request_iterator)
        if data[0].request_data == "error":
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            return test_server_pb2.Response()
        response = test_server_pb2.Response(
            server_id=SERVER_ID, response_data="data"
        )
        return response

    def ServerStreamingMethod(self, request, context):
        if request.request_data == "error":
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="server stream error",
            )
            return test_server_pb2.Response()

        # create a generator
        def response_messages():
            for _ in range(5):
                response = test_server_pb2.Response(
                    server_id=SERVER_ID, response_data="data"
                )
                yield response

        return response_messages()

    def BidirectionalStreamingMethod(self, request_iterator, context):
        data = list(request_iterator)
        if data[0].request_data == "error":
            context.abort(
                code=grpc.StatusCode.INVALID_ARGUMENT,
                details="bidirectional error",
            )
            return

        for _ in range(5):
            yield test_server_pb2.Response(
                server_id=SERVER_ID, response_data="data"
            )


def create_test_server(port):
    # pylint: disable=consider-using-with
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))

    test_server_pb2_grpc.add_GRPCTestServerServicer_to_server(
        TestServer(), server
    )

    server.add_insecure_port(f"localhost:{port}")

    return server
