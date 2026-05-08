# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from opentelemetry.sdk.extension.aws.trace import (  # pylint: disable=no-name-in-module
    AwsXRayIdGenerator,
)

id_generator = AwsXRayIdGenerator()


def test_generate_xray_trace_id(benchmark):
    benchmark(id_generator.generate_trace_id)


def test_generate_xray_span_id(benchmark):
    benchmark(id_generator.generate_span_id)
