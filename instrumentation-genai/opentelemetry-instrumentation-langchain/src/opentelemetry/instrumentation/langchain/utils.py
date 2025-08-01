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

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

def dont_throw(func: F) -> F:
    """
    Decorator that catches and logs exceptions, rather than re-raising them,
    to avoid interfering with user code if instrumentation fails.
    """
    def wrapper(*args: Any, **kwargs: Any) -> Optional[Any]:
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
    return wrapper  # type: ignore
