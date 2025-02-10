import google.genai

from .version import __version__ as _LIBRARY_VERSION
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics


_LIBRARY_NAME = 'opentelemetry-instrumentation-google-genai'
_SCHEMA_URL = Schemas.V1_30_0.value
_SCOPE_ATTRIBUTES = {
    'gcp.client.name': 'google.genai',
    'gcp.client.repo': 'googleapis/python-genai',
    'gcp.client.version': google.genai.__version__,
}


class OTelWrapper:

    def __init__(
        self,
        tracer,
        event_logger,
        meter):
        self._tracer = tracer
        self._event_logger = event_logger
        self._meter = meter
        self._operation_duration_metric = gen_ai_metrics.create_gen_ai_client_operation_duration(meter)
        self._token_usage_metric = gen_ai_metrics.create_gen_ai_client_token_usage(meter)
 
    @staticmethod
    def from_providers(
        tracer_provider,
        event_logger_provider,
        meter_provider):
        return OTelWrapper(
            tracer_provider.get_tracer(_LIBRARY_NAME, _LIBRARY_VERSION, _SCHEMA_URL, _SCOPE_ATTRIBUTES),
            event_logger_provider.get_event_logger(_LIBRARY_NAME, _LIBRARY_VERSION, _SCHEMA_URL, _SCOPE_ATTRIBUTES),
            meter = meter_provider.get_meter(_LIBRARY_NAME, _LIBRARY_VERSION, _SCHEMA_URL, _SCOPE_ATTRIBUTES),
        )

    @property
    def tracer(self):
        return self._tracer
    
    @property
    def event_logger(self):
        return self._event_logger

    @property
    def meter(self):
        return self._meter

    @property
    def operation_duration_metric(self):
        return self._operation_duration_metric

    @property
    def token_usage_metric(self):
        return self._token_usage_metric
