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

from typing import Any, Collection, Optional

from opentelemetry._events import get_event_logger_provider
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.metrics import get_meter_provider
from opentelemetry.trace import get_tracer_provider
from opentelemetry.util.genai.completion_hook import load_completion_hook

from .allowlist_util import AllowList
from .generate_content import (
    instrument_generate_content,
    uninstrument_generate_content,
)
from .otel_wrapper import OTelWrapper


class GoogleGenAiSdkInstrumentor(BaseInstrumentor):
    def __init__(
        self, generate_content_config_key_allowlist: Optional[AllowList] = None
    ):
        self._generate_content_snapshot = None
        self._generate_content_config_key_allowlist = (
            generate_content_config_key_allowlist
            or AllowList.from_env(
                "OTEL_GOOGLE_GENAI_GENERATE_CONTENT_CONFIG_INCLUDES",
                excludes_env_var="OTEL_GOOGLE_GENAI_GENERATE_CONTENT_CONFIG_EXCLUDES",
            )
        )

    # Inherited, abstract function from 'BaseInstrumentor'. Even though 'self' is
    # not used in the definition, a method is required per the API contract.
    def instrumentation_dependencies(self) -> Collection[str]:  # pylint: disable=no-self-use
        return ["google-genai>=1.0.0,<2"]

    def _instrument(self, **kwargs: Any):
        tracer_provider = (
            kwargs.get("tracer_provider") or get_tracer_provider()
        )
        event_logger_provider = (
            kwargs.get("event_logger_provider") or get_event_logger_provider()
        )
        meter_provider = kwargs.get("meter_provider") or get_meter_provider()
        otel_wrapper = OTelWrapper.from_providers(
            tracer_provider=tracer_provider,
            event_logger_provider=event_logger_provider,
            meter_provider=meter_provider,
        )
        completion_hook = kwargs.get("completion_hook") or load_completion_hook()
        self._generate_content_snapshot = instrument_generate_content(
            otel_wrapper,
            completion_hook,
            generate_content_config_key_allowlist=self._generate_content_config_key_allowlist,
        )

    def _uninstrument(self, **kwargs: Any):
        uninstrument_generate_content(self._generate_content_snapshot)
