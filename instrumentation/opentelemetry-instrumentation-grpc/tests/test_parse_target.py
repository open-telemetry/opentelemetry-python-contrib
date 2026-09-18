# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import pytest

from opentelemetry.instrumentation.grpc._client import _parse_target


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        # host:port targets, with and without a resolver scheme
        ("localhost:50051", ("localhost", 50051)),
        ("dns:///localhost:4317", ("localhost", 4317)),
        ("[::1]:50051", ("::1", 50051)),
        ("dns:///[::1]:50051", ("::1", 50051)),
        # a bare host has no port
        ("myhost", ("myhost", None)),
        # non-network targets carry no host/port and must not be parsed as one
        ("unix:/tmp/grpc.sock", (None, None)),
        ("unix:///tmp/grpc.sock", (None, None)),
        ("unix-abstract:grpc.sock", (None, None)),
        ("vsock:2:12345", (None, None)),
        # unparseable or empty targets fall back to no attributes
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_target(target, expected):
    assert _parse_target(target) == expected
