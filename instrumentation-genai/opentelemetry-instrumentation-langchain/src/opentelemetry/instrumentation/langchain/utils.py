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

from opentelemetry._events import Event
from opentelemetry.semconv._incubating.attributes import gen_ai_attributes as GenAI

logger = logging.getLogger(__name__)

# By default, we do not record prompt or completion content. Set this
# environment variable to "true" to enable collection of message text.
OTEL_INSTRUMENTATION_LANGCHAIN_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_LANGCHAIN_CAPTURE_MESSAGE_CONTENT"
)


def should_collect_content() -> bool:
    val = os.getenv(OTEL_INSTRUMENTATION_LANGCHAIN_CAPTURE_MESSAGE_CONTENT, "false")
    return val.strip().lower() == "true"


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

def get_property_value(obj, property_name):
    if isinstance(obj, dict):
        return obj.get(property_name, None)

    return getattr(obj, property_name, None)

def message_to_event(message, system):
    content = get_property_value(message, "content")
    if should_collect_content() and content is not None:
        type = get_property_value(message, "type")
        if type == "human":
            type = "user"
        body = {}
        body["content"] = content
        attributes = {
            # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
            "gen_ai.framework": "langchain",
            GenAI.GEN_AI_SYSTEM: system
        }

        return Event(
            name=f"gen_ai.{type}.message",
            attributes=attributes,
            body=body if body else None,
        )

def chat_generation_to_event(chat_generation, index, system):
    if should_collect_content() and chat_generation.message:
        content = get_property_value(chat_generation.message, "content")
        if content is not None:
            attributes = {
                # TODO: add below to opentelemetry.semconv._incubating.attributes.gen_ai_attributes
                "gen_ai.framework": "langchain",
                GenAI.GEN_AI_SYSTEM: system
            }

            finish_reason = None
            generation_info = chat_generation.generation_info
            if generation_info is not None:
                finish_reason = generation_info.get("finish_reason")

            message = {
                "content": content,
                "type": chat_generation.type
            }
            body = {
                "index": index,
                "finish_reason": finish_reason or "error",
                "message": message
            }

            return Event(
                name="gen_ai.choice",
                attributes=attributes,
                body=body,
            )
