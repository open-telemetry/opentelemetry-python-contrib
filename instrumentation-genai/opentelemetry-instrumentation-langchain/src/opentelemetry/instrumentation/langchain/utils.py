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

"""Utility functions for LangChain instrumentation."""

from __future__ import annotations

import dataclasses
import datetime
import importlib.util
import json
import logging
import os
import traceback
from typing import Any, Callable, TypeVar

from opentelemetry import context as context_api
from opentelemetry._logs import Logger

from opentelemetry.instrumentation.langchain.config import Config

OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = (
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
)

F = TypeVar("F", bound=Callable[..., Any])


class CallbackFilteredJSONEncoder(json.JSONEncoder):
    """JSON encoder that filters out callback objects and handles special types."""

    def default(self, o: Any) -> Any:
        if isinstance(o, dict):
            if "callbacks" in o:
                o = dict(o)
                del o["callbacks"]
                return o

        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)

        if hasattr(o, "to_json"):
            return o.to_json()

        # Handle pydantic models if available
        if hasattr(o, "model_dump_json"):
            return o.model_dump_json()

        if isinstance(o, datetime.datetime):
            return o.isoformat()

        try:
            return str(o)
        except Exception:
            logger = logging.getLogger(__name__)
            logger.debug(
                "Failed to serialize object of type: %s", type(o).__name__
            )
            return ""


def should_send_prompts() -> bool:
    """Check if prompt/content tracing is enabled.

    Returns:
        True if content tracing is enabled via environment variable or context.
    """
    env_value = os.getenv(OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false")
    return env_value.lower() == "true" or bool(
        context_api.get_value("override_enable_content_tracing")
    )


def dont_throw(func: F) -> F:
    """Decorator that wraps a function and logs exceptions instead of throwing.

    This ensures instrumentation errors don't affect the instrumented application.

    Args:
        func: The function to wrap.

    Returns:
        The wrapped function that catches and logs exceptions.
    """
    logger = logging.getLogger(func.__module__)

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.debug(
                "OpenTelemetry LangChain instrumentation failed in %s, error: %s",
                func.__name__,
                traceback.format_exc(),
            )
            if Config.exception_logger:
                Config.exception_logger(e)
            return None

    return wrapper  # type: ignore[return-value]


def should_emit_events() -> bool:
    """Check if event emission is enabled.

    Events are emitted when not using legacy attributes and event logger is set.

    Returns:
        True if events should be emitted.
    """
    return not Config.use_legacy_attributes and isinstance(
        Config.event_logger, Logger
    )


def is_package_available(package_name: str) -> bool:
    """Check if a Python package is available for import.

    Args:
        package_name: The name of the package to check.

    Returns:
        True if the package is available.
    """
    return importlib.util.find_spec(package_name) is not None
