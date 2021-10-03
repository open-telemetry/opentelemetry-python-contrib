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
#

"""
OpenTelemetry SDK configuration helpers
"""

from typing import Any, Sequence

from opentelemetry import trace
from opentelemetry.conf.components import (
    _import_exporters_from_env,
    _import_id_generator_from_env,
    _import_tracer_provider_from_env,
)
from opentelemetry.conf.types import (
    SpanExporterFactory,
    SpanProcessorFactory,
    TracerProviderFactory,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_tracing(
    provider_factory: TracerProviderFactory = None,
    processor_factories: Sequence[SpanProcessorFactory] = None,
    exporter_factories: Sequence[SpanExporterFactory] = None,
    set_global: bool = True,
) -> TracerProvider:
    """configure_tracing is a convenience function used to quickly setup an OpenTelemetry SDK tracing pipeline."""

    # default factories
    processor_factories = processor_factories or [BatchSpanProcessor]
    provider_factory = provider_factory or _import_tracer_provider_from_env()
    exporter_factories = exporter_factories or _import_exporters_from_env()

    # provider dependencies other than IdGenerator are automatially
    # sourced from env such as span limits and resources.
    provider = provider_factory(id_generator=_import_id_generator_from_env()())

    # for each exporter, create a SpanProcessor and add it to the provider
    for exporter_factory in exporter_factories:
        for processor_factory in processor_factories:
            processor = processor_factory(exporter_factory())
            provider.add_span_processor(processor)

    # set as the global tracer provider if requested
    if set_global:
        trace.set_tracer_provider(provider)

    return provider


def _is_global_tracing_pipeline_set():
    tracer = trace.get_tracer("opentelemetry.conf")
    return not isinstance(tracer, trace.ProxyTracer)
