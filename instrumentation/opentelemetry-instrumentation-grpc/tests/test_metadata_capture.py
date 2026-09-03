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

"""Tests for rpc.request.header / rpc.response.header / rpc.response.trailer."""

from concurrent import futures
from unittest import IsolatedAsyncioTestCase, mock

import grpc
import wrapt

from opentelemetry.instrumentation._semconv import (
    OTEL_SEMCONV_STABILITY_OPT_IN,
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.instrumentation.grpc import (
    aio_client_interceptors,
    aio_server_interceptor,
    client_interceptor,
    server_interceptor,
)
from opentelemetry.instrumentation.grpc._semconv import (
    RPC_REQUEST_HEADER_TEMPLATE,
    RPC_RESPONSE_HEADER_TEMPLATE,
    RPC_RESPONSE_TRAILER_TEMPLATE,
    _ClientMetadataCapture,
    _MetadataCapture,
    _ServerMetadataCapture,
)
from opentelemetry.instrumentation.grpc.grpcext import intercept_channel
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.test.test_base import TestBase
from opentelemetry.trace import SpanKind

from .protobuf import test_server_pb2, test_server_pb2_grpc
from .protobuf.test_server_pb2 import Request
from .protobuf.test_server_pb2_grpc import (
    GRPCTestServerServicer,
    add_GRPCTestServerServicer_to_server,
)

_PORT = 25566
_TARGET = f"localhost:{_PORT}"

# gRPC base64-encodes `-bin` values on the wire and hands back the raw bytes,
# so this exercises the round trip, not just the encoder.
_BINARY_VALUE = b"\x00\xff"
_BINARY_VALUE_B64 = "AP8="

_REQUEST_METADATA = (
    ("x-tenant-id", "acme"),
    ("x-secret", "do-not-capture"),
    ("x-trace-bin", _BINARY_VALUE),
)
_INITIAL_METADATA = (("x-response-id", "resp-1"),)
_TRAILING_METADATA = (("x-cost", "42"),)


class _MetadataServer(test_server_pb2_grpc.GRPCTestServerServicer):
    # pylint: disable=invalid-name,no-self-use

    def SimpleMethod(self, request, context):
        context.send_initial_metadata(_INITIAL_METADATA)
        context.set_trailing_metadata(_TRAILING_METADATA)
        return test_server_pb2.Response(server_id=1, response_data="data")


class TestMetadataCaptureUnit(TestBase):
    def test_only_configured_keys_are_captured(self):
        capture = _MetadataCapture(
            RPC_REQUEST_HEADER_TEMPLATE, ["x-tenant-id"]
        )
        self.assertEqual(
            capture.collect(_REQUEST_METADATA),
            {"rpc.request.header.x-tenant-id": ["acme"]},
        )

    def test_keys_are_matched_case_insensitively(self):
        capture = _MetadataCapture(
            RPC_REQUEST_HEADER_TEMPLATE, [" X-Tenant-Id "]
        )
        self.assertEqual(
            capture.collect((("X-TENANT-ID", "acme"),)),
            {"rpc.request.header.x-tenant-id": ["acme"]},
        )

    def test_repeated_keys_become_a_list(self):
        capture = _MetadataCapture(RPC_REQUEST_HEADER_TEMPLATE, ["x-fwd"])
        self.assertEqual(
            capture.collect((("x-fwd", "1.2.3.4"), ("x-fwd", "1.2.3.5"))),
            {"rpc.request.header.x-fwd": ["1.2.3.4", "1.2.3.5"]},
        )

    def test_binary_metadata_is_base64_encoded(self):
        capture = _MetadataCapture(
            RPC_REQUEST_HEADER_TEMPLATE, ["x-trace-bin"]
        )
        self.assertEqual(
            capture.collect((("x-trace-bin", b"\x00\xff"),)),
            {"rpc.request.header.x-trace-bin": ["AP8="]},
        )

    def test_nothing_configured_captures_nothing(self):
        capture = _MetadataCapture(RPC_REQUEST_HEADER_TEMPLATE, [])
        self.assertFalse(capture)
        self.assertEqual(capture.collect(_REQUEST_METADATA), {})

    def test_explicit_keys_win_over_environment(self):
        with mock.patch.dict(
            "os.environ",
            {
                "OTEL_INSTRUMENTATION_GRPC_CAPTURE_CLIENT_REQUEST_HEADERS": "x-secret"
            },
        ):
            capture = _ClientMetadataCapture(request_headers=["x-tenant-id"])
        self.assertEqual(
            capture.request_headers.collect(_REQUEST_METADATA),
            {"rpc.request.header.x-tenant-id": ["acme"]},
        )

    def test_environment_configures_each_attribute(self):
        with mock.patch.dict(
            "os.environ",
            {
                "OTEL_INSTRUMENTATION_GRPC_CAPTURE_SERVER_REQUEST_HEADERS": "x-tenant-id",
                "OTEL_INSTRUMENTATION_GRPC_CAPTURE_SERVER_RESPONSE_HEADERS": "x-response-id",
                "OTEL_INSTRUMENTATION_GRPC_CAPTURE_SERVER_RESPONSE_TRAILERS": "x-cost",
            },
        ):
            capture = _ServerMetadataCapture()
        self.assertEqual(
            capture.request_headers.collect(_REQUEST_METADATA),
            {"rpc.request.header.x-tenant-id": ["acme"]},
        )
        self.assertEqual(
            capture.response_headers.collect(_INITIAL_METADATA),
            {"rpc.response.header.x-response-id": ["resp-1"]},
        )
        self.assertEqual(
            capture.response_trailers.collect(_TRAILING_METADATA),
            {"rpc.response.trailer.x-cost": ["42"]},
        )


class _MetadataCaptureBase(TestBase):
    """Runs one unary RPC through both interceptors with capture configured."""

    _opt_in = "rpc"

    def setUp(self):
        super().setUp()
        # Other modules in this suite leave grpc globally instrumented, which
        # would wrap this test's channel and server with a second,
        # unconfigured interceptor.
        for module, name in (
            (grpc, "insecure_channel"),
            (grpc, "secure_channel"),
        ):
            while isinstance(getattr(module, name, None), wrapt.ObjectProxy):
                unwrap(module, name)
        with mock.patch.dict(
            "os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: self._opt_in}
        ):
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            capture_kwargs = {
                "capture_request_headers": ["x-tenant-id", "x-trace-bin"],
                "capture_response_headers": ["x-response-id"],
                "capture_response_trailers": ["x-cost"],
            }
            self._server = grpc.server(
                futures.ThreadPoolExecutor(max_workers=1),
                interceptors=[server_interceptor(**capture_kwargs)],
            )
            test_server_pb2_grpc.add_GRPCTestServerServicer_to_server(
                _MetadataServer(), self._server
            )
            self._server.add_insecure_port(_TARGET)
            self._server.start()

            self._channel = intercept_channel(
                grpc.insecure_channel(_TARGET),
                client_interceptor(
                    host="localhost", port=_PORT, **capture_kwargs
                ),
            )
        self._stub = test_server_pb2_grpc.GRPCTestServerStub(self._channel)

    def tearDown(self):
        super().tearDown()
        self._channel.close()
        self._server.stop(None)
        _OpenTelemetrySemanticConventionStability._initialized = False

    def _call(self):
        self.memory_exporter.clear()
        self._stub.SimpleMethod(
            Request(client_id=1, request_data="data"),
            metadata=_REQUEST_METADATA,
        )
        spans = self.memory_exporter.get_finished_spans()
        # Other modules in this suite leave grpc globally instrumented and
        # never fully undo it, so one RPC can produce several client spans.
        # Ours is the one from the interceptor configured in setUp, which is
        # the only one carrying the captured metadata.
        client = max(
            (s for s in spans if s.kind is SpanKind.CLIENT),
            key=lambda s: len(s.attributes),
        )
        server = max(
            (s for s in spans if s.kind is SpanKind.SERVER),
            key=lambda s: len(s.attributes),
        )
        return client, server


class TestMetadataCaptureNewSemconv(_MetadataCaptureBase):
    def test_client_span_records_headers_and_trailers(self):
        client, _ = self._call()
        self.assertEqual(
            client.attributes[
                RPC_REQUEST_HEADER_TEMPLATE.format("x-tenant-id")
            ],
            ("acme",),
        )
        self.assertEqual(
            client.attributes[
                RPC_RESPONSE_HEADER_TEMPLATE.format("x-response-id")
            ],
            ("resp-1",),
        )
        self.assertEqual(
            client.attributes[RPC_RESPONSE_TRAILER_TEMPLATE.format("x-cost")],
            ("42",),
        )
        self.assertEqual(
            client.attributes[
                RPC_REQUEST_HEADER_TEMPLATE.format("x-trace-bin")
            ],
            (_BINARY_VALUE_B64,),
        )

    def test_server_span_records_headers_and_trailers(self):
        _, server = self._call()
        self.assertEqual(
            server.attributes[
                RPC_REQUEST_HEADER_TEMPLATE.format("x-tenant-id")
            ],
            ("acme",),
        )
        self.assertEqual(
            server.attributes[
                RPC_RESPONSE_HEADER_TEMPLATE.format("x-response-id")
            ],
            ("resp-1",),
        )
        self.assertEqual(
            server.attributes[RPC_RESPONSE_TRAILER_TEMPLATE.format("x-cost")],
            ("42",),
        )
        self.assertEqual(
            server.attributes[
                RPC_REQUEST_HEADER_TEMPLATE.format("x-trace-bin")
            ],
            (_BINARY_VALUE_B64,),
        )

    def test_unlisted_metadata_is_not_recorded(self):
        client, server = self._call()
        for span in (client, server):
            self.assertNotIn(
                RPC_REQUEST_HEADER_TEMPLATE.format("x-secret"),
                span.attributes,
            )


class TestMetadataCaptureOldSemconv(_MetadataCaptureBase):
    """Capture is a new-conventions feature and must stay off by default."""

    _opt_in = ""

    def test_no_metadata_attributes_on_old_semconv(self):
        client, server = self._call()
        for span in (client, server):
            for name in span.attributes:
                self.assertFalse(
                    name.startswith("rpc.request.header.")
                    or name.startswith("rpc.response.header.")
                    or name.startswith("rpc.response.trailer.")
                )


class _AioMetadataServer(GRPCTestServerServicer):
    # pylint: disable=invalid-name,no-self-use

    async def SimpleMethod(self, request, context):
        await context.send_initial_metadata(_INITIAL_METADATA)
        context.set_trailing_metadata(_TRAILING_METADATA)
        return test_server_pb2.Response(server_id=1, response_data="data")


class TestAioMetadataCapture(TestBase, IsolatedAsyncioTestCase):
    """The aio client reads response metadata through awaitables."""

    def setUp(self):
        super().setUp()
        with mock.patch.dict(
            "os.environ", {OTEL_SEMCONV_STABILITY_OPT_IN: "rpc"}
        ):
            _OpenTelemetrySemanticConventionStability._initialized = False
            _OpenTelemetrySemanticConventionStability._initialize()
            self._capture_kwargs = {
                "capture_request_headers": ["x-tenant-id", "x-trace-bin"],
                "capture_response_headers": ["x-response-id"],
                "capture_response_trailers": ["x-cost"],
            }
            self._server_interceptor = aio_server_interceptor(
                **self._capture_kwargs
            )
            self._client_interceptors = aio_client_interceptors(
                host="localhost", port=_PORT, **self._capture_kwargs
            )

    def tearDown(self):
        super().tearDown()
        _OpenTelemetrySemanticConventionStability._initialized = False

    async def _call(self):
        server = grpc.aio.server(interceptors=[self._server_interceptor])
        add_GRPCTestServerServicer_to_server(_AioMetadataServer(), server)
        port = server.add_insecure_port("[::]:0")
        await server.start()
        try:
            async with grpc.aio.insecure_channel(
                f"localhost:{port:d}", interceptors=self._client_interceptors
            ) as channel:
                await channel.unary_unary(
                    "/GRPCTestServer/SimpleMethod",
                    request_serializer=Request.SerializeToString,
                    response_deserializer=test_server_pb2.Response.FromString,
                )(
                    Request(client_id=1, request_data="data"),
                    metadata=grpc.aio.Metadata(*_REQUEST_METADATA),
                )
        finally:
            await server.stop(None)
        spans = self.memory_exporter.get_finished_spans()
        client = max(
            (s for s in spans if s.kind is SpanKind.CLIENT),
            key=lambda s: len(s.attributes),
        )
        server_span = max(
            (s for s in spans if s.kind is SpanKind.SERVER),
            key=lambda s: len(s.attributes),
        )
        return client, server_span

    async def test_aio_spans_record_headers_and_trailers(self):
        client, server_span = await self._call()
        for span in (client, server_span):
            self.assertEqual(
                span.attributes[
                    RPC_REQUEST_HEADER_TEMPLATE.format("x-tenant-id")
                ],
                ("acme",),
            )
            self.assertEqual(
                span.attributes[
                    RPC_RESPONSE_HEADER_TEMPLATE.format("x-response-id")
                ],
                ("resp-1",),
            )
            self.assertEqual(
                span.attributes[
                    RPC_RESPONSE_TRAILER_TEMPLATE.format("x-cost")
                ],
                ("42",),
            )
