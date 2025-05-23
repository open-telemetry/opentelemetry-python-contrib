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

"""
OpenAI client instrumentation supporting `openai`, it can be enabled by
using ``OpenAIInstrumentor``.

.. _openai: https://pypi.org/project/openai/

Usage
-----

.. code:: python

    from openai import OpenAI
    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": "Write a short poem on open telemetry."},
        ],
    )

API
---
"""

import json
from typing import Collection

from wrapt import wrap_function_wrapper

from opentelemetry._events import get_event_logger, Event
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.openai_v2.package import _instruments
from opentelemetry.instrumentation.openai_v2.utils import is_content_enabled
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.metrics import get_meter
from opentelemetry.semconv.schemas import Schemas
from opentelemetry.trace import get_tracer
from opentelemetry._logs.severity import SeverityNumber

from .instruments import Instruments
from .patch import async_chat_completions_create, chat_completions_create


class OpenAIInstrumentor(BaseInstrumentor):
    def __init__(self):
        self._meter = None

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def record_prompt_content(self, span, prompt_body):
        """Default prompt hook."""

        prompt_event = None

        if self.content_enabled:
            # TODO: perf - check if DEBUG is enabled
            prompt_event = Event(
                "gen_ai.request.inputs",
                body=prompt_body, # note, semconvs are switching to event attributes instead of body, so this is temporary
                attributes={
                    "gen_ai.system": "openai",
                },
                severity_number=SeverityNumber.DEBUG,
            )
            
            if self.capture_verbose_attributes and span.is_recording():
                span.set_attribute("gen_ai.request.inputs", json.dumps(prompt_body, ensure_ascii=False))
            
        if self.custom_prompt_hook:
            try:  
                self.custom_prompt_hook(span, prompt_event, prompt_body)
            except Exception as e:
                # TODO - proper internal logging                
                print(f"Error in prompt hook, turning it off: {e}")
                self.custom_prompt_hook = None
                pass
        
        # prompt hook can modify the event, so we need to emit it after the hook is called    
        if prompt_event:
            self.event_logger.emit(prompt_event)            

    def record_completion_content(self, span, completion_body):
        """Default completion hook."""

        completion_event = None
        if self.content_enabled:
            # TODO: perf - check if DEBUG is enabled            
            completion_event = Event(
                "gen_ai.response.outputs",
                body=completion_body, # note, semconvs are switching to event attributes instead of body, so this is temporary
                attributes={
                    "gen_ai.system": "openai",
                },
                severity_number=SeverityNumber.DEBUG,
            )

            if self.capture_verbose_attributes and span.is_recording():
                span.set_attribute("gen_ai.response.outputs", json.dumps(completion_body, ensure_ascii=False))

        if self.custom_completion_hook:
            try:  
                self.custom_completion_hook(span, completion_event, completion_body)
            except Exception as e:
                # TODO - proper internal logging
                print(f"Error in completion hook, turning it off: {e}")
                self.custom_completion_hook = None                
                pass

        # completion hook can modify the event, so we need to emit it after the hook is called                
        if completion_event:
            self.event_logger.emit(completion_event)

    def _instrument(self, **kwargs):
        """Enable OpenAI instrumentation."""
        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            "",
            tracer_provider,
            schema_url=Schemas.V1_28_0.value,
        )
        event_logger_provider = kwargs.get("event_logger_provider")
        self.event_logger = get_event_logger(
            __name__,
            "",
            schema_url=Schemas.V1_28_0.value,
            event_logger_provider=event_logger_provider,
        )
        meter_provider = kwargs.get("meter_provider")
        self._meter = get_meter(
            __name__,
            "",
            meter_provider,
            schema_url=Schemas.V1_28_0.value,
        )

        instruments = Instruments(self._meter)

        self.capture_verbose_attributes = kwargs.get("capture_verbose_attributes", True)
        
        self.content_enabled = is_content_enabled() or kwargs.get("capture_sensitive_content", False)
        self.custom_prompt_hook = kwargs.get("prompt_hook")
        self.custom_completion_hook = kwargs.get("completion_hook")

        prompt_hook = None
        if self.content_enabled or self.custom_prompt_hook:
            prompt_hook = self.record_prompt_content
            
        completion_hook = None
        if self.content_enabled or self.custom_completion_hook:
            completion_hook = self.record_completion_content

        wrap_function_wrapper(
            module="openai.resources.chat.completions",
            name="Completions.create",
            wrapper=chat_completions_create(
                tracer, self.event_logger, instruments, prompt_hook, completion_hook, self.capture_verbose_attributes
            ),
        )

        wrap_function_wrapper(
            module="openai.resources.chat.completions",
            name="AsyncCompletions.create",
            wrapper=async_chat_completions_create(
                tracer, self.event_logger, instruments, prompt_hook, completion_hook, self.capture_verbose_attributes
            ),
        )

    def _uninstrument(self, **kwargs):
        import openai  # pylint: disable=import-outside-toplevel

        unwrap(openai.resources.chat.completions.Completions, "create")
        unwrap(openai.resources.chat.completions.AsyncCompletions, "create")
