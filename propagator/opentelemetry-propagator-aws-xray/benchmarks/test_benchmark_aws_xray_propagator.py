# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from requests.structures import CaseInsensitiveDict

from opentelemetry.propagators.aws.aws_xray_propagator import (
    TRACE_HEADER_KEY,
    AwsXRayPropagator,
)

XRAY_PROPAGATOR = AwsXRayPropagator()


def test_extract_single_header(benchmark):
    benchmark(
        XRAY_PROPAGATOR.extract,
        {
            TRACE_HEADER_KEY: "bdb5b63237ed38aea578af665aa5aa60-00000000000000000c32d953d73ad225"
        },
    )


def test_inject_empty_context(benchmark):
    benchmark(
        XRAY_PROPAGATOR.inject, {}, setter=CaseInsensitiveDict.__setitem__
    )
