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

from concurrent import futures
import time

import grpc

from .protobuf import test_server_pb2, test_server_pb2_grpc

SERVER_ID = 1


class TestServer(test_server_pb2_grpc.GRPCTestServerServicer):
    # pylint: disable=invalid-name
    # pylint: disable=no-self-use

    def SimpleMethod(self, request, context):
        if request.request_data == "abort":
            context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, request.request_data
            )
        elif request.request_data == "cancel":
            context.cancel()
            return test_server_pb2.Response()
        elif request.request_data == "error":
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(request.request_data)
            return test_server_pb2.Response()
        elif request.request_data == "exception":
            raise ValueError(request.request_data)
        elif request.request_data == "sleep":
            time.sleep(0.5)

        return test_server_pb2.Response(
            server_id=SERVER_ID, response_data="data"
        )

    def ClientStreamingMethod(self, request_iterator, context):
        data = list(request_iterator)

        if data[0].request_data == "abort":
            context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, data[0].request_data
            )
        elif data[0].request_data == "cancel":
            context.cancel()
            return test_server_pb2.Response()
        elif data[0].request_data == "error":
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(data[0].request_data)
            return test_server_pb2.Response()
        elif data[0].request_data == "exception":
            raise ValueError(data[0].request_data)
        elif data[0].request_data == "sleep":
            time.sleep(0.5)

        return test_server_pb2.Response(
            server_id=SERVER_ID, response_data="data"
        )

    def ServerStreamingMethod(self, request, context):

        yield test_server_pb2.Response(
            server_id=SERVER_ID, response_data="data"
        )

        if request.request_data == "abort":
            context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, request.request_data
            )
        elif request.request_data == "cancel":
            context.cancel()
            return test_server_pb2.Response()
        elif request.request_data == "error":
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(request.request_data)
            return test_server_pb2.Response()
        elif request.request_data == "exception":
            raise ValueError(request.request_data)
        elif request.request_data == "sleep":
            time.sleep(0.5)

        for _ in range(5):
            yield test_server_pb2.Response(
                server_id=SERVER_ID, response_data="data"
            )

    def BidirectionalStreamingMethod(self, request_iterator, context):
        data = list(request_iterator)

        yield test_server_pb2.Response(
            server_id=SERVER_ID, response_data="data"
        )

        if data[0].request_data == "abort":
            context.abort(
                grpc.StatusCode.FAILED_PRECONDITION, data[0].request_data
            )
        elif data[0].request_data == "cancel":
            context.cancel()
            return
        elif data[0].request_data == "error":
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(data[0].request_data)
            return
        elif data[0].request_data == "exception":
            raise ValueError(data[0].request_data)
        elif data[0].request_data == "sleep":
            time.sleep(0.5)

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
