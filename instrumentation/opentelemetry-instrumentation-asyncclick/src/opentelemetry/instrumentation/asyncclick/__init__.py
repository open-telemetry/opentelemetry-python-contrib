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
Instrument `asyncclick`_ CLI applications. The instrumentor will avoid instrumenting
well-known servers (e.g. *flask run* and *uvicorn*) to avoid unexpected effects
like every request having the same Trace ID.



.. _asyncclick: https://pypi.org/project/asyncclick/

Usage
-----

.. code-block:: python

    import asyncio
    import asyncclick
    from opentelemetry.instrumentation.asyncclick import AsyncClickInstrumentor

    AsyncClickInstrumentor().instrument()

    @asyncclick.command()
    async def hello():
        asyncclick.echo(f'Hello world!')

    if __name__ == "__main__":
        asyncio.run(hello())

API
---
"""

from __future__ import annotations

import os
import sys
from functools import partial
from logging import getLogger
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Collection,
    TypeVar,
)

import asyncclick
from typing_extensions import ParamSpec, Unpack
from wrapt import (
    wrap_function_wrapper,  # type: ignore[reportUnknownVariableType]
)

from opentelemetry import trace
from opentelemetry.instrumentation.asyncclick.package import _instruments
from opentelemetry.instrumentation.asyncclick.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import (
    unwrap,
)
from opentelemetry.semconv._incubating.attributes.process_attributes import (
    PROCESS_COMMAND_ARGS,
    PROCESS_EXECUTABLE_NAME,
    PROCESS_EXIT_CODE,
    PROCESS_PID,
)
from opentelemetry.semconv.attributes.error_attributes import ERROR_TYPE
from opentelemetry.trace.status import StatusCode

if TYPE_CHECKING:
    from typing import TypedDict

    class InstrumentKwargs(TypedDict, total=False):
        tracer_provider: trace.TracerProvider

    class UninstrumentKwargs(TypedDict, total=False):
        pass


_logger = getLogger(__name__)


T = TypeVar("T")
P = ParamSpec("P")


async def _command_invoke_wrapper(
    wrapped: Callable[P, Awaitable[T]],
    instance: asyncclick.core.Command,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    tracer: trace.Tracer,
) -> T:
    # Subclasses of Command include groups and CLI runners, but
    # we only want to instrument the actual commands which are
    # instances of Command itself.
    if instance.__class__ != asyncclick.Command:
        return await wrapped(*args, **kwargs)

    ctx = args[0]

    span_name = ctx.info_name
    span_attributes = {
        PROCESS_COMMAND_ARGS: sys.argv,
        PROCESS_EXECUTABLE_NAME: sys.argv[0],
        PROCESS_EXIT_CODE: 0,
        PROCESS_PID: os.getpid(),
    }

    with tracer.start_as_current_span(
        name=span_name,
        kind=trace.SpanKind.INTERNAL,
        attributes=span_attributes,
    ) as span:
        try:
            result = await wrapped(*args, **kwargs)
            return result
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            if span.is_recording():
                span.set_attribute(ERROR_TYPE, type(exc).__qualname__)
                span.set_attribute(
                    PROCESS_EXIT_CODE, getattr(exc, "exit_code", 1)
                )
            raise


# pylint: disable=no-self-use
class AsyncClickInstrumentor(BaseInstrumentor):
    """An instrumentor for asyncclick"""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Unpack[InstrumentKwargs]) -> None:
        tracer_provider = kwargs.get("tracer_provider")
        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider,
        )

        wrap_function_wrapper(
            asyncclick.core.Command,
            "invoke",
            partial(_command_invoke_wrapper, tracer=tracer),
        )

    def _uninstrument(self, **kwargs: Unpack["UninstrumentKwargs"]) -> None:
        unwrap(asyncclick.core.Command, "invoke")
