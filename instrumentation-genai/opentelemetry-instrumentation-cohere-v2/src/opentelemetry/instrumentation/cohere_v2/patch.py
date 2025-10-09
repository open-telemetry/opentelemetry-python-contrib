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

from opentelemetry._events import EventLogger
from opentelemetry.trace import SpanKind, Tracer
from opentelemetry.instrumentation.genai_utils import (
    get_span_name,
    handle_span_exception
)
from opentelemetry.instrumentation.utils import is_instrumentation_enabled
from .utils import (
    get_genai_request_attributes,
    message_to_event,
    set_response_attributes,
    set_server_address_and_port,
)


def client_chat(
    tracer: Tracer, event_logger: EventLogger, capture_content: bool
):
    """Wrap the `chat` method of the `ClientV2` class to trace it."""

    def traced_method(wrapped, instance, args, kwargs):
        if not is_instrumentation_enabled():
            return wrapped(*args, **kwargs)

        span_attributes = {**get_genai_request_attributes(kwargs, instance)}
        set_server_address_and_port(instance, span_attributes)
        span_name = get_span_name(span_attributes)

        with tracer.start_as_current_span(
            name=span_name,
            kind=SpanKind.CLIENT,
            attributes=span_attributes,
        ) as span:
            if span.is_recording():
                for message in kwargs.get("messages", []):
                    event_logger.emit(
                        message_to_event(message, capture_content)
                    )

            try:
                result = wrapped(*args, **kwargs)
                if span.is_recording():
                    set_response_attributes(
                        span, result, event_logger, capture_content
                    )
                return result

            except Exception as error:
                handle_span_exception(span, error)
                raise

    return traced_method
