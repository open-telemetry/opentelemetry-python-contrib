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

from os import environ
from typing import Sequence, Tuple

from pkg_resources import iter_entry_points

from opentelemetry import trace
from opentelemetry.conf.types import SpanExporterFactory, TracerProviderFactory
from opentelemetry.environment_variables import (
    OTEL_PYTHON_ID_GENERATOR,
    OTEL_PYTHON_TRACER_PROVIDER,
    OTEL_TRACES_EXPORTER,
)
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator

_EXPORTER_OTLP = "otlp"
_EXPORTER_OTLP_SPAN = "otlp_proto_grpc_span"
_DEFAULT_TRACER_PROVIDER = "sdk_tracer_provider"
_DEFAULT_SPAN_EXPORTER = _EXPORTER_OTLP_SPAN
_DEFAULT_ID_GENERATOR = "random"


def _import_tracer_provider_from_env() -> TracerProviderFactory:
    tracer_provider_name = environ.get(
        OTEL_PYTHON_TRACER_PROVIDER, _DEFAULT_TRACER_PROVIDER
    ).strip()
    provider_impl = _import_tracer_provider_config_components(
        [tracer_provider_name], "opentelemetry_tracer_provider"
    )[0][1]
    if issubclass(provider_impl, trace.TracerProvider):
        return provider_impl
    raise RuntimeError(f"{tracer_provider_name} is not a TracerProvider")


def _get_exporter_names() -> Sequence[str]:
    trace_exporters = environ.get(OTEL_TRACES_EXPORTER, _DEFAULT_SPAN_EXPORTER)
    exporters = set()
    if trace_exporters and trace_exporters.lower().strip() != "none":
        exporters.update(
            {
                trace_exporter.strip()
                for trace_exporter in trace_exporters.split(",")
            }
        )
    if _EXPORTER_OTLP in exporters:
        exporters.remove(_EXPORTER_OTLP)
        exporters.add(_EXPORTER_OTLP_SPAN)
    return list(exporters)


def _import_exporters_from_env() -> Sequence[SpanExporterFactory]:
    exporter_names = _get_exporter_names()
    for (
        exporter_name,
        exporter_impl,
    ) in _import_tracer_provider_config_components(
        exporter_names, "opentelemetry_traces_exporter"
    ):
        if issubclass(exporter_impl, SpanExporter):
            yield exporter_impl
        else:
            raise RuntimeError(f"{exporter_name} is not a trace exporter")


def _import_id_generator_from_env() -> IdGenerator:
    id_generator_name = environ.get(
        OTEL_PYTHON_ID_GENERATOR, _DEFAULT_ID_GENERATOR
    ).strip()
    id_generator_impl = _import_tracer_provider_config_components(
        [id_generator_name], "opentelemetry_id_generator"
    )[0][1]

    if issubclass(id_generator_impl, IdGenerator):
        return id_generator_impl
    raise RuntimeError(f"{id_generator_name} is not an IdGenerator")


def _import_tracer_provider_config_components(
    selected_components, entry_point_name
) -> Sequence[Tuple[str, object]]:
    component_entry_points = {
        ep.name: ep for ep in iter_entry_points(entry_point_name)
    }
    component_impls = []
    for selected_component in selected_components:
        entry_point = component_entry_points.get(selected_component, None)
        if not entry_point:
            raise RuntimeError(
                f"Requested component '{selected_component}' not found in entry points for '{entry_point_name}'"
            )
        component_impl = entry_point.load()
        component_impls.append((selected_component, component_impl))
    return component_impls
