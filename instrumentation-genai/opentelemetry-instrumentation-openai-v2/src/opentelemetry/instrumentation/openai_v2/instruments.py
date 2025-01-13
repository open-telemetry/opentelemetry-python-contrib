from opentelemetry.semconv._incubating.metrics import gen_ai_metrics


class Instruments:
    def __init__(self, meter):
        self.operation_duration_histogram = (
            gen_ai_metrics.create_gen_ai_client_operation_duration(meter)
        )
        self.token_usage_histogram = (
            gen_ai_metrics.create_gen_ai_client_token_usage(meter)
        )
