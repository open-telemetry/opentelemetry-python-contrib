# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from opentelemetry.propagators.aws.aws_xray_propagator import (
    AwsXRayLambdaPropagator,
    AwsXRayPropagator,
)

__all__ = ["AwsXRayPropagator", "AwsXRayLambdaPropagator"]
