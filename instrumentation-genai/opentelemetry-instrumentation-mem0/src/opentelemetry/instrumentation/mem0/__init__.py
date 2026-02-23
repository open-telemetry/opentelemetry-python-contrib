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
OpenTelemetry Mem0 Instrumentation
===================================

Instrumentation for the Mem0 Python SDK memory operations.

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.mem0 import Mem0Instrumentor
    from mem0 import Memory

    # Enable instrumentation
    Mem0Instrumentor().instrument()

    # Use Mem0 normally — all memory operations are now traced
    m = Memory()
    m.add("I prefer dark mode", user_id="alice")
    results = m.search("preferences", user_id="alice")

Configuration
-------------

Memory content capture can be enabled by setting the environment variable:
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true``

API
---
"""

from typing import Any, Collection

from wrapt import wrap_function_wrapper

from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.mem0.package import _instruments
from opentelemetry.instrumentation.mem0.patch import (
    wrap_memory_add,
    wrap_memory_delete,
    wrap_memory_delete_all,
    wrap_memory_get_all,
    wrap_memory_search,
    wrap_memory_update,
)
from opentelemetry.instrumentation.utils import unwrap


class Mem0Instrumentor(BaseInstrumentor):
    """An instrumentor for the Mem0 Python SDK.

    This instrumentor traces Mem0 memory operations (add, search, update,
    delete) and emits spans with GenAI memory semantic convention attributes.
    """

    def __init__(self) -> None:
        super().__init__()

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        tracer_provider = kwargs.get("tracer_provider")

        wrap_function_wrapper(
            module="mem0.memory.main",
            name="Memory.add",
            wrapper=wrap_memory_add(tracer_provider),
        )
        wrap_function_wrapper(
            module="mem0.memory.main",
            name="Memory.search",
            wrapper=wrap_memory_search(tracer_provider),
        )
        wrap_function_wrapper(
            module="mem0.memory.main",
            name="Memory.update",
            wrapper=wrap_memory_update(tracer_provider),
        )
        wrap_function_wrapper(
            module="mem0.memory.main",
            name="Memory.delete",
            wrapper=wrap_memory_delete(tracer_provider),
        )
        wrap_function_wrapper(
            module="mem0.memory.main",
            name="Memory.delete_all",
            wrapper=wrap_memory_delete_all(tracer_provider),
        )
        wrap_function_wrapper(
            module="mem0.memory.main",
            name="Memory.get_all",
            wrapper=wrap_memory_get_all(tracer_provider),
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        import mem0.memory.main  # noqa: PLC0415

        for method in (
            "add",
            "search",
            "update",
            "delete",
            "delete_all",
            "get_all",
        ):
            unwrap(mem0.memory.main.Memory, method)
