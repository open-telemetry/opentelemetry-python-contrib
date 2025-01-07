class Meters:
    def __init__(self, meter):
        self.operation_duration_histogram = meter.create_histogram(
            name="gen_ai.client.operation.duration",
            description="Duration of gen_ai client operations",
            unit="seconds",
        )
        self.token_usage_histogram = meter.create_histogram(
            name="gen_ai.client.token.usage",
            description="Token usage of gen_ai client operations",
            unit="tokens",
        )
