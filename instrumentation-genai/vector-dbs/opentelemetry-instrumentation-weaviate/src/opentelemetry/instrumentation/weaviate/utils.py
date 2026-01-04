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

"""Utility functions for Weaviate instrumentation."""

import functools
import json
import logging
import traceback
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class Config:
    """Configuration for the Weaviate instrumentation."""

    exception_logger: Optional[Callable[[Exception], None]] = None


def dont_throw(func: F) -> F:
    """Decorator that prevents exceptions from propagating.

    This ensures that instrumentation errors don't affect the application.
    Exceptions are logged at debug level.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if Config.exception_logger:
                Config.exception_logger(e)
            else:
                logger.debug(
                    "Exception in instrumentation: %s\n%s",
                    str(e),
                    traceback.format_exc(),
                )
            return None

    return wrapper  # type: ignore[return-value]


class ArgsGetter:
    """Helper to get arguments regardless of whether passed as args or kwargs.

    Additionally, serializes dicts/lists to JSON strings for span attributes.
    """

    def __init__(self, args: tuple, kwargs: dict):
        self.args = args
        self.kwargs = kwargs

    def __call__(self, index: int, name: str) -> Optional[str]:
        """Get argument by position or name and serialize to JSON.

        Args:
            index: The positional index of the argument
            name: The keyword argument name

        Returns:
            JSON-serialized string of the argument, or None if not found
        """
        try:
            obj = self.args[index]
        except IndexError:
            obj = self.kwargs.get(name)

        if obj is None:
            return None

        try:
            return json.dumps(obj, default=str)
        except (TypeError, ValueError) as e:
            logger.debug(
                "Failed to serialize argument (%s) (%s) to JSON: %s",
                index,
                name,
                e,
            )
            return None
