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

import logging
import os
import traceback

logger = logging.getLogger(__name__)

# By default, we do not record prompt or completion content. Set this
# environment variable to "true" to enable collection of message text.
OTEL_INSTRUMENTATION_LANGCHAIN_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_LANGCHAIN_CAPTURE_MESSAGE_CONTENT"
)

OTEL_INSTRUMENTATION_GENAI_EXPORTER = "OTEL_INSTRUMENTATION_GENAI_EXPORTER"

OTEL_INSTRUMENTATION_GENAI_EVALUATION_FRAMEWORK = (
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_FRAMEWORK"
)

OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE = (
    "OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE"
)


def should_collect_content() -> bool:
    val = os.getenv(
        OTEL_INSTRUMENTATION_LANGCHAIN_CAPTURE_MESSAGE_CONTENT, "false"
    )
    return val.strip().lower() == "true"


def should_emit_events() -> bool:
    val = os.getenv(
        OTEL_INSTRUMENTATION_GENAI_EXPORTER, "SpanMetricEventExporter"
    )
    if val.strip().lower() == "spanmetriceventexporter":
        return True
    elif val.strip().lower() == "spanmetricexporter":
        return False
    else:
        raise ValueError(f"Unknown exporter_type: {val}")


def should_enable_evaluation() -> bool:
    val = os.getenv(OTEL_INSTRUMENTATION_GENAI_EVALUATION_ENABLE, "True")
    return val.strip().lower() == "true"


def get_evaluation_framework_name() -> str:
    val = os.getenv(
        OTEL_INSTRUMENTATION_GENAI_EVALUATION_FRAMEWORK, "Deepeval"
    )
    return val.strip().lower()


def get_property_value(obj, property_name):
    if isinstance(obj, dict):
        return obj.get(property_name, None)

    return getattr(obj, property_name, None)


def dont_throw(func):
    """
    Decorator that catches and logs exceptions, rather than re-raising them,
    to avoid interfering with user code if instrumentation fails.
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.debug(
                "OpenTelemetry instrumentation for LangChain encountered an error in %s: %s",
                func.__name__,
                traceback.format_exc(),
            )
            from opentelemetry.instrumentation.langchain.config import Config

            if Config.exception_logger:
                Config.exception_logger(e)
            return None

    return wrapper
