from opentelemetry.trace import (
    get_tracer_provider,
    set_tracer_provider
)
from opentelemetry._logs import (
    get_logger_provider,
    set_logger_provider
)
from opentelemetry.metrics import (
    get_meter_provider,
    set_meter_provider
)

from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk._logs._internal import SynchronousMultiLogRecordProcessor
from opentelemetry.sdk._logs._internal.export.in_memory_log_exporter import InMemoryLogExporter
from opentelemetry.sdk.metrics._internal.export import InMemoryMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor


class OTelProviderSnapshot:

    def __init__(self):
        self._tracer_provider = get_tracer_provider()
        self._logger_provider = get_logger_provider()
        self._meter_provider = get_meter_provider()

    def restore(self):
        set_tracer_provider(self._tracer_provider)
        set_logger_provider(self._logger_provider)
        set_meter_provider(self._meter_provider)


class OTelMocker:

    def __init__(self):
        self._snapshot = None
        self._logs = InMemoryLogExporter()
        self._traces = InMemorySpanExporter()
        self._metrics = InMemoryMetricReader()

    def install(self):
        self._snapshot = OTelProviderSnapshot()
        self._install_logs()
        self._install_metrics()
        self._install_traces()

    def uninstall(self):
        self._snapshot.restore()

    def get_finished_logs(self):
        return self._logs.get_finished_logs()
    
    def get_finished_spans(self):
        return self._traces.get_finished_spans()

    def get_metrics_data(self):
        return self._metrics.get_metrics_data()

    def get_span_named(self, name):
        for span in self.get_finished_spans():
            if span.name == name:
                return span
        return None
        
    def assert_has_span_named(self, name):
        span = self.get_span_named(name)
        assert span is not None, f'Could not find span named {name}; finished spans: {self.get_finished_spans()}'

    def _install_logs(self):
        processor = SynchronousMultiLogRecordProcessor()
        processor.add_log_record_processor(SimpleLogRecordProcessor(self._logs))
        provider = LoggerProvider(processor)
        set_logger_provider(provider)

    def _install_metrics(self):
        provider = MeterProvider(metric_readers=[self._metrics])
        set_meter_provider(provider)

    def _install_traces(self):
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self._traces))
        set_tracer_provider(provider)

