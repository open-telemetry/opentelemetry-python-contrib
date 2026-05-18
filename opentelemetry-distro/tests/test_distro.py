# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

import os
from unittest import TestCase, mock

from opentelemetry.distro import OpenTelemetryDistro
from opentelemetry.environment_variables import (
    OTEL_METRICS_EXPORTER,
    OTEL_TRACES_EXPORTER,
)
from opentelemetry.sdk.environment_variables import OTEL_EXPORTER_OTLP_PROTOCOL
from opentelemetry.util._importlib_metadata import (
    PackageNotFoundError,
    version,
)


class TestDistribution(TestCase):
    def test_package_available(self):
        try:
            version("opentelemetry-distro")
        except PackageNotFoundError:
            self.fail("opentelemetry-distro not installed")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_default_configuration(self):
        distro = OpenTelemetryDistro()
        distro.configure()
        self.assertEqual("otlp", os.environ.get(OTEL_TRACES_EXPORTER))
        self.assertEqual("otlp", os.environ.get(OTEL_METRICS_EXPORTER))
        self.assertEqual("grpc", os.environ.get(OTEL_EXPORTER_OTLP_PROTOCOL))
