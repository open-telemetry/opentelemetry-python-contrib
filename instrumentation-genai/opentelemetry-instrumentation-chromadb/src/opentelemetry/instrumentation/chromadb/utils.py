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

"""Utility functions for ChromaDB instrumentation."""

import functools
import logging
import traceback
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class Config:
    """Configuration for the ChromaDB instrumentation."""

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


def count_or_none(obj: Any) -> Optional[int]:
    """Return the length of an object or None if not iterable."""
    if obj is not None:
        try:
            return len(obj)
        except TypeError:
            pass
    return None


def to_string_or_none(obj: Any) -> Optional[str]:
    """Convert an object to a string or return None."""
    if obj is None:
        return None
    try:
        return str(obj)
    except Exception:
        return None
