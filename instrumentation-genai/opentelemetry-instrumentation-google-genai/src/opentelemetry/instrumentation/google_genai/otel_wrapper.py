

class OTelWrapper:

    def __init__(
        self,
        tracer,
        event_logger,
        meter):
        self._tracer = tracer
        self._event_logger = event_logger
        self._meter = meter
 
    @staticmethod
    def from_providers(
        tracer_provider,
        event_logger_provider,
        meter_provider):