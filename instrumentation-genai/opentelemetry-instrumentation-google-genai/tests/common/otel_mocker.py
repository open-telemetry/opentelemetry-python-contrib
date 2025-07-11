# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import opentelemetry._events
import opentelemetry._logs._internal
import opentelemetry.metrics._internal
import opentelemetry.trace
from opentelemetry._events import (
    get_event_logger_provider,
    set_event_logger_provider,
)
from opentelemetry._logs import get_logger_provider, set_logger_provider
from opentelemetry.metrics import get_meter_provider, set_meter_provider
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics._internal.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import get_tracer_provider, set_tracer_provider
from opentelemetry.util._once import Once


def _bypass_otel_once():
    opentelemetry.trace._TRACER_PROVIDER_SET_ONCE = Once()
    opentelemetry._logs._internal._LOGGER_PROVIDER_SET_ONCE = Once()
    opentelemetry._events._EVENT_LOGGER_PROVIDER_SET_ONCE = Once()
    opentelemetry.metrics._internal._METER_PROVIDER_SET_ONCE = Once()


class OTelProviderSnapshot:
    def __init__(self):
        self._tracer_provider = get_tracer_provider()
        self._logger_provider = get_logger_provider()
        self._event_logger_provider = get_event_logger_provider()
        self._meter_provider = get_meter_provider()

    def restore(self):
        _bypass_otel_once()
        set_tracer_provider(self._tracer_provider)
        set_logger_provider(self._logger_provider)
        set_event_logger_provider(self._event_logger_provider)
        set_meter_provider(self._meter_provider)


class _LogWrapper:
    def __init__(self, log_record):
        self._log_record = log_record

    @property
    def scope(self):
        return self._log_record.instrumentation_scope

    @property
    def resource(self):
        return self._log_record.resource

    @property
    def attributes(self):
        return self._log_record.attributes

    @property
    def body(self):
        return self._log_record.body

    def __str__(self):
        return self._log_record.to_json()


class _MetricDataPointWrapper:
    def __init__(self, resource, scope, metric):
        self._resource = resource
        self._scope = scope
        self._metric = metric

    @property
    def resource(self):
        return self._resource

    @property
    def scope(self):
        return self._scope

    @property
    def metric(self):
        return self._metric

    @property
    def name(self):
        return self._metric.name

    @property
    def data(self):
        return self._metric.data


class OTelMocker:
    def __init__(self):
        self._snapshot = None
        self._logs = InMemoryLogExporter()
        self._traces = InMemorySpanExporter()
        self._metrics = InMemoryMetricReader()
        self._spans = []
        self._finished_logs = []
        self._metrics_data = []

    def install(self):
        self._snapshot = OTelProviderSnapshot()
        _bypass_otel_once()
        self._install_logs()
        self._install_metrics()
        self._install_traces()

    def uninstall(self):
        self._snapshot.restore()

    def get_finished_logs(self):
        for log_data in self._logs.get_finished_logs():
            self._finished_logs.append(_LogWrapper(log_data))
        return self._finished_logs

    def get_finished_spans(self):
        for span in self._traces.get_finished_spans():
            self._spans.append(span)
        return self._spans

    def get_metrics_data(self):
        data = self._metrics.get_metrics_data()
        if data is not None:
            for resource_metric in data.resource_metrics:
                resource = resource_metric.resource
                for scope_metrics in resource_metric.scope_metrics:
                    scope = scope_metrics.scope
                    for metric in scope_metrics.metrics:
                        wrapper = _MetricDataPointWrapper(
                            resource, scope, metric
                        )
                        self._metrics_data.append(wrapper)
        return self._metrics_data

    def get_span_named(self, name):
        for span in self.get_finished_spans():
            if span.name == name:
                return span
        return None

    def assert_has_span_named(self, name):
        span = self.get_span_named(name)
        finished_spans = [span.name for span in self.get_finished_spans()]
        assert (
            span is not None
        ), f'Could not find span named "{name}"; finished spans: {finished_spans}'

    def assert_does_not_have_span_named(self, name):
        span = self.get_span_named(name)
        assert span is None, f"Found unexpected span named {name}"

    def get_event_named(self, event_name):
        for event in self.get_finished_logs():
            event_name_attr = event.attributes.get("event.name")
            if event_name_attr is None:
                continue
            if event_name_attr == event_name:
                return event
        return None

    def get_events_named(self, event_name):
        result = []
        for event in self.get_finished_logs():
            event_name_attr = event.attributes.get("event.name")
            if event_name_attr is None:
                continue
            if event_name_attr == event_name:
                result.append(event)
        return result

    def assert_has_event_named(self, name):
        event = self.get_event_named(name)
        finished_logs = self.get_finished_logs()
        assert (
            event is not None
        ), f'Could not find event named "{name}"; finished logs: {finished_logs}'

    def assert_does_not_have_event_named(self, name):
        event = self.get_event_named(name)
        assert event is None, f"Unexpected event: {event}"

    def get_metrics_data_named(self, name):
        results = []
        for entry in self.get_metrics_data():
            if entry.name == name:
                results.append(entry)
        return results

    def assert_has_metrics_data_named(self, name):
        data = self.get_metrics_data_named(name)
        assert len(data) > 0

    def _install_logs(self):
        provider = LoggerProvider()
        provider.add_log_record_processor(SimpleLogRecordProcessor(self._logs))
        set_logger_provider(provider)
        event_provider = EventLoggerProvider(logger_provider=provider)
        set_event_logger_provider(event_provider)

    def _install_metrics(self):
        provider = MeterProvider(metric_readers=[self._metrics])
        set_meter_provider(provider)

    def _install_traces(self):
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self._traces))
        set_tracer_provider(provider)
