# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
"""
Instrument the ibmmq and pymqi clients to trace IBM MQ applications.

Usage
-----

.. code-block:: python

    import pymqi
    from opentelemetry.instrumentation.ibmmq import IbmMqInstrumentor

    IbmMqInstrumentor().instrument()

    qmgr = pymqi.connect("QM1")
    queue = pymqi.Queue(qmgr, "DEV.QUEUE.1")
    queue.put(b"Hello World!")
    queue.close()
    qmgr.disconnect()

Whichever of ``ibmmq`` (IBM's official client) or ``pymqi`` is installed gets
instrumented; both get instrumented if both are installed. Producer spans are
created for ``QueueManager.put1`` and ``Queue.put``, consumer spans for
``Queue.get`` and, on ``ibmmq`` only, for callbacks registered through the
async MQCB API.

Two extra attributes are available but off by default, because neither is a
ratified OpenTelemetry semantic convention yet:
``messaging.ibmmq.queue_manager.id``, the identifier IBM MQ assigns to a
queue manager and which is unique across every queue manager anywhere, and
``messaging.ibmmq.browse``, which marks a get that only browsed a message
instead of consuming it. Set the environment variable
``OTEL_PYTHON_IBMMQ_EXPERIMENTAL_SPAN_ATTRIBUTES`` to ``true`` or ``1`` to
enable both:

.. code-block:: sh

    export OTEL_PYTHON_IBMMQ_EXPERIMENTAL_SPAN_ATTRIBUTES=true

API
---
"""

from collections.abc import Collection
from importlib import import_module
from importlib.metadata import PackageNotFoundError, distribution
from typing import Any

import wrapt

from opentelemetry import trace
from opentelemetry.instrumentation.ibmmq import utils
from opentelemetry.instrumentation.ibmmq.package import (
    _instruments_any,
    _instruments_ibmmq,
    _instruments_pymqi,
)
from opentelemetry.instrumentation.ibmmq.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.trace import Tracer

# Clients this package knows how to instrument, tried in order at
# _instrument() time. Both get instrumented if both happen to be installed.
_CLIENT_MODULE_NAMES = ("ibmmq", "pymqi")


def _wrap_client(client: Any, tracer: Tracer) -> list[tuple[Any, str]]:
    """Apply every wrap for one client module (ibmmq or pymqi).

    Returns the (target, method_name) pairs that were wrapped, so
    _uninstrument can unwrap exactly these later.
    """
    cmqc = client.CMQC
    qmgr_cls = client.QueueManager
    queue_cls = client.Queue
    wrapped: list[tuple[Any, str]] = []

    connect_wrapper = utils.make_connect_wrapper(cmqc)
    # connect_tcp_client is deliberately not wrapped: in both real clients it
    # ends by calling self.connect_with_options(name, **kwargs), so wrapping
    # both would perform the QMID MQINQ resolve twice per TCP client connect.
    for method_name in ("connect", "connect_with_options"):
        wrapt.wrap_function_wrapper(qmgr_cls, method_name, connect_wrapper)
        wrapped.append((qmgr_cls, method_name))

    wrapt.wrap_function_wrapper(qmgr_cls, "put1", utils.make_put1_wrapper(tracer))
    wrapped.append((qmgr_cls, "put1"))

    wrapt.wrap_function_wrapper(queue_cls, "put", utils.make_queue_put_wrapper(tracer))
    wrapped.append((queue_cls, "put"))

    wrapt.wrap_function_wrapper(queue_cls, "get", utils.make_queue_get_wrapper(tracer, cmqc))
    wrapped.append((queue_cls, "get"))

    # Async MQCB registration only exists on ibmmq, not on pymqi.
    cb_wrapper = utils.make_cb_wrapper(tracer, cmqc)
    for target in (queue_cls, qmgr_cls):
        if hasattr(target, "cb"):
            wrapt.wrap_function_wrapper(target, "cb", cb_wrapper)
            wrapped.append((target, "cb"))

    return wrapped


class IbmMqInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        # Determine which package is installed: IBM's official ibmmq client
        # or its predecessor pymqi. Both expose the same shape, so either
        # one is instrumented the same way.
        try:
            distribution("ibmmq")
            return (_instruments_ibmmq,)
        except PackageNotFoundError:
            pass

        try:
            distribution("pymqi")
            return (_instruments_pymqi,)
        except PackageNotFoundError:
            pass

        return _instruments_any

    def _instrument(self, **kwargs: Any) -> None:
        tracer_provider = kwargs.get("tracer_provider")
        tracer = trace.get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )
        utils.configure_experimental_attributes()

        wrapped: list[tuple[Any, str]] = []
        for module_name in _CLIENT_MODULE_NAMES:
            try:
                client = import_module(module_name)
            except ImportError:
                continue
            wrapped.extend(_wrap_client(client, tracer))
        self._wrapped = wrapped
        utils.set_instrumented(True)

    def _uninstrument(self, **kwargs: Any) -> None:
        utils.set_instrumented(False)
        for target, method_name in getattr(self, "_wrapped", []):
            unwrap(target, method_name)
        self._wrapped = []


__all__ = ["IbmMqInstrumentor", "__version__"]
