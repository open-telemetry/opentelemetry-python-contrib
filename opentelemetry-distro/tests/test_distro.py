# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
# type: ignore

import os
from platform import python_implementation
from unittest import TestCase, mock, skipIf

from opentelemetry.distro import OpenTelemetryDistro
from opentelemetry.environment_variables import (
    OTEL_LOGS_EXPORTER,
    OTEL_METRICS_EXPORTER,
    OTEL_TRACES_EXPORTER,
)
from opentelemetry.sdk._configuration import _get_exporter_names, _import_exporters
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
        self.assertEqual("otlp", os.environ.get(OTEL_LOGS_EXPORTER))
        self.assertEqual("grpc", os.environ.get(OTEL_EXPORTER_OTLP_PROTOCOL))

    @mock.patch.dict("os.environ", {}, clear=True)
    @skipIf(python_implementation() == "PyPy", "gRPC exporters are tested on CPython")
    def test_default_exporter_entry_points(self):
        OpenTelemetryDistro().configure()

        trace_exporters, metric_exporters, log_exporters = _import_exporters(
            _get_exporter_names("traces"),
            _get_exporter_names("metrics"),
            _get_exporter_names("logs"),
        )

        self.assertEqual(["otlp_proto_grpc"], list(trace_exporters))
        self.assertEqual(["otlp_proto_grpc"], list(metric_exporters))
        self.assertEqual(["otlp_proto_grpc"], list(log_exporters))
