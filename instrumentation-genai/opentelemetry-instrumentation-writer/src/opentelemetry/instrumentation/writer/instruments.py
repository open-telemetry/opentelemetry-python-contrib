# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from opentelemetry.metrics import Histogram, Meter
from opentelemetry.util.genai.instruments import (
    create_duration_histogram,
    create_token_histogram,
)


class Instruments:
    """GenAI histograms shared by the Writer instrumentation.

    The histograms are created through ``opentelemetry.util.genai.instruments``
    so the metric names, units, and bucket boundaries match the shared GenAI
    telemetry layer.
    """

    def __init__(self, meter: Meter) -> None:
        self.operation_duration_histogram: Histogram = (
            create_duration_histogram(meter)
        )
        self.token_usage_histogram: Histogram = create_token_histogram(meter)
