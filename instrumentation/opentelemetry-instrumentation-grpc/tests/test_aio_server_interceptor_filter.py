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
import asyncio

try:
    from unittest import IsolatedAsyncioTestCase
except ImportError:
    # unittest.IsolatedAsyncioTestCase was introduced in Python 3.8. It's use
    # simplifies the following tests. Without it, the amount of test code
    # increases significantly, with most of the additional code handling
    # the asyncio set up.
    from unittest import TestCase

    class IsolatedAsyncioTestCase(TestCase):
        def run(self, result=None):
            self.skipTest(
                "This test requires Python 3.8 for unittest.IsolatedAsyncioTestCase"
            )


import grpc
import grpc.aio
import pytest

import opentelemetry.instrumentation.grpc
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import (
    GrpcAioInstrumentorServer,
    aio_server_interceptor,
    filters,
)
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import StatusCode

from .protobuf.test_server_pb2 import Request, Response
from .protobuf.test_server_pb2_grpc import (
    GRPCTestServerServicer,
    add_GRPCTestServerServicer_to_server,
)
from .test_aio_server_interceptor import Servicer, run_with_test_server

# pylint:disable=unused-argument
# pylint:disable=no-self-use


@pytest.mark.asyncio
class TestOpenTelemetryAioServerInterceptor(TestBase, IsolatedAsyncioTestCase):
    async def test_instrumentor(self):
        """Check that automatic instrumentation configures the interceptor"""
        rpc_call = "/GRPCTestServer/SimpleMethod"

        grpc_aio_server_instrumentor = GrpcAioInstrumentorServer(
            filter_=filters.method_name("NotSimpleMethod")
        )
        try:
            grpc_aio_server_instrumentor.instrument()

            async def request(channel):
                request = Request(client_id=1, request_data="test")
                msg = request.SerializeToString()
                return await channel.unary_unary(rpc_call)(msg)

            await run_with_test_server(request, add_interceptor=False)

            spans_list = self.memory_exporter.get_finished_spans()
            self.assertEqual(len(spans_list), 0)

        finally:
            grpc_aio_server_instrumentor.uninstrument()
