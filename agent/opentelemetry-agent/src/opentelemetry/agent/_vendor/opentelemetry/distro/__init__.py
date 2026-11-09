# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os

from opentelemetry.agent._vendor.opentelemetry.environment_variables import (
    OTEL_LOGS_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_TRACES_EXPORTER,
)
from opentelemetry.agent._vendor.opentelemetry.instrumentation.distro import BaseDistro
from opentelemetry.agent._vendor.opentelemetry.sdk._configuration import _OTelSDKConfigurator
from opentelemetry.agent._vendor.opentelemetry.sdk.environment_variables import OTEL_EXPORTER_OTLP_PROTOCOL


class OpenTelemetryConfigurator(_OTelSDKConfigurator):
    pass


class OpenTelemetryDistro(BaseDistro):
    """
    The OpenTelemetry provided Distro configures a default set of
    configuration out of the box.
    """

    # pylint: disable=no-self-use
    def _configure(self, **kwargs):
        os.environ.setdefault(OTEL_TRACES_EXPORTER, "otlp")
        os.environ.setdefault(OTEL_METRICS_EXPORTER, "otlp")
        os.environ.setdefault(OTEL_LOGS_EXPORTER, "otlp")
        # opentelemetry-agent: the gRPC exporters aren't vendored (grpcio has no pure-Python wheel).
        os.environ.setdefault(OTEL_EXPORTER_OTLP_PROTOCOL, "http/protobuf")
