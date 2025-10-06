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
from __future__ import annotations

import logging
from typing import Any

import google.genai

from opentelemetry._events import Event, EventLogger, EventLoggerProvider
from opentelemetry.metrics import Meter, MeterProvider
from opentelemetry.semconv._incubating.metrics import gen_ai_metrics
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import Tracer, TracerProvider

from .version import __version__ as _LIBRARY_VERSION

_logger = logging.getLogger(__name__)

_SCOPE_NAME = "opentelemetry.instrumentation.google_genai"
_PYPI_PACKAGE_NAME = "opentelemetry-instrumentation-google-genai"
_SCHEMA_URL = Schemas.V1_30_0.value
_SCOPE_ATTRIBUTES = {
    "gcp.client.name": "google.genai",
    "gcp.client.repo": "googleapis/python-genai",
    "gcp.client.version": google.genai.__version__,
    "pypi.package.name": _PYPI_PACKAGE_NAME,
}


class OTelWrapper:
    def __init__(
        self, tracer: Tracer, event_logger: EventLogger, meter: Meter
    ):
        self._tracer = tracer
        self._event_logger = event_logger
        self._meter = meter
        self._operation_duration_metric = (
            gen_ai_metrics.create_gen_ai_client_operation_duration(meter)
        )
        self._token_usage_metric = (
            gen_ai_metrics.create_gen_ai_client_token_usage(meter)
        )

    @staticmethod
    def from_providers(
        tracer_provider: TracerProvider,
        event_logger_provider: EventLoggerProvider,
        meter_provider: MeterProvider,
    ):
        return OTelWrapper(
            tracer_provider.get_tracer(
                _SCOPE_NAME, _LIBRARY_VERSION, _SCHEMA_URL, _SCOPE_ATTRIBUTES
            ),
            event_logger_provider.get_event_logger(
                _SCOPE_NAME, _LIBRARY_VERSION, _SCHEMA_URL, _SCOPE_ATTRIBUTES
            ),
            meter=meter_provider.get_meter(
                _SCOPE_NAME, _LIBRARY_VERSION, _SCHEMA_URL, _SCOPE_ATTRIBUTES
            ),
        )

    def start_as_current_span(self, *args, **kwargs):
        return self._tracer.start_as_current_span(*args, **kwargs)

    @property
    def operation_duration_metric(self):
        return self._operation_duration_metric

    @property
    def token_usage_metric(self):
        return self._token_usage_metric

    def log_system_prompt(
        self, attributes: dict[str, str], body: dict[str, Any]
    ):
        _logger.debug("Recording system prompt.")
        event_name = "gen_ai.system.message"
        self._log_event(event_name, attributes, body)

    def log_user_prompt(
        self, attributes: dict[str, str], body: dict[str, Any]
    ):
        _logger.debug("Recording user prompt.")
        event_name = "gen_ai.user.message"
        self._log_event(event_name, attributes, body)

    def log_response_content(
        self, attributes: dict[str, str], body: dict[str, Any]
    ):
        _logger.debug("Recording response.")
        event_name = "gen_ai.choice"
        self._log_event(event_name, attributes, body)

    def _log_event(
        self, event_name: str, attributes: dict[str, str], body: dict[str, Any]
    ):
        event = Event(event_name, body=body, attributes=attributes)
        self._event_logger.emit(event)

    def log_completion_details(
        self,
        event: Event,
    ) -> None:
        _logger.debug("Recording completion details event.")
        self._event_logger.emit(event)
