# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from opentelemetry.metrics import Histogram, Meter
from opentelemetry.util.genai.instruments import (
    create_duration_histogram,
    create_token_histogram,
)


class Instruments:
    def __init__(self, meter: Meter):
        self.operation_duration_histogram: Histogram = (
            create_duration_histogram(meter)
        )
        self.token_usage_histogram: Histogram = create_token_histogram(meter)
