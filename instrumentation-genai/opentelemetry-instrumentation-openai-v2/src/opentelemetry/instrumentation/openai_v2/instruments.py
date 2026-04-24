from opentelemetry.metrics import Histogram, Meter
from opentelemetry.util.genai.instruments import (
    create_duration_histogram,
    create_token_histogram,
    create_ttfc_histogram,
)


class Instruments:
    def __init__(self, meter: Meter):
        self.operation_duration_histogram: Histogram = create_duration_histogram(meter)
        self.token_usage_histogram: Histogram = create_token_histogram(meter)
        self.ttfc_histogram: Histogram = create_ttfc_histogram(meter)
