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
import traceback
from typing import Any, Callable, Optional, TypeVar

R = TypeVar("R")


def dont_throw(func: Callable[..., R]) -> Callable[..., Optional[R]]:
    """
    A decorator that wraps the passed in function and logs exceptions instead of throwing them.

    @param func: The function to wrap
    @return: The wrapper function
    """
    # Obtain a logger specific to the function's module
    logger = logging.getLogger(func.__module__)

    def wrapper(*args: Any, **kwargs: Any) -> Optional[R]:
        try:
            return func(*args, **kwargs)
        except Exception:  # pylint: disable=broad-except
            logger.debug(
                "failed to trace in %s, error: %s",
                func.__name__,
                traceback.format_exc(),
            )
        return None

    return wrapper
