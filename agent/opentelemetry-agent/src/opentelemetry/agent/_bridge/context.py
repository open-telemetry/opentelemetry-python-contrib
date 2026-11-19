# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""The application's runtime context, stored in the vendored one.

The application's ``opentelemetry.context`` loads `BridgeRuntimeContext` while it's being imported
(``OTEL_PYTHON_CONTEXT``), so only its ``opentelemetry.context.context`` module is imported here.

Both APIs create their context keys with ``create_key()``, which makes them unique: the application's
keys of the current span, baggage and instrumentation suppression are translated to the vendored
ones. They're looked up in the application's modules once those have defined them; other keys are
kept as they are.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from contextvars import Token
from dataclasses import dataclass
from typing import cast

from opentelemetry.agent._bridge import release_environment_variable
from opentelemetry.agent._vendor.opentelemetry import baggage as agent_baggage
from opentelemetry.agent._vendor.opentelemetry import context as agent_context
from opentelemetry.agent._vendor.opentelemetry.context.context import Context as AgentContext
from opentelemetry.agent._vendor.opentelemetry.environment_variables import OTEL_PYTHON_CONTEXT
from opentelemetry.agent._vendor.opentelemetry.trace import propagation as agent_trace_propagation
from opentelemetry.context.context import Context, _RuntimeContext

_Convert = Callable[[object], object]


def _identity(value: object) -> object:
    return value


def _span_converters() -> tuple[_Convert, _Convert]:
    # Imports the application's opentelemetry.trace.span, loaded by the time it defines the span key.
    from opentelemetry.agent._bridge import span  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

    return span.to_app_span, span.to_agent_span


def _no_converters() -> tuple[_Convert, _Convert]:
    return _identity, _identity


@dataclass(frozen=True)
class _KeyBridge:
    module: str
    """The application's module that defines the key."""
    attribute: str
    agent_key: str
    converters: Callable[[], tuple[_Convert, _Convert]]
    """Return the value converters to the application's and the vendored API; called once the key is found."""


_KEY_BRIDGES = (
    _KeyBridge("opentelemetry.trace.propagation", "_SPAN_KEY", agent_trace_propagation._SPAN_KEY, _span_converters),
    _KeyBridge("opentelemetry.baggage", "_BAGGAGE_KEY", agent_baggage._BAGGAGE_KEY, _no_converters),
    _KeyBridge(
        "opentelemetry.context",
        "_SUPPRESS_INSTRUMENTATION_KEY",
        agent_context._SUPPRESS_INSTRUMENTATION_KEY,
        _no_converters,
    ),
    # Not defined by opentelemetry-api versions before 1.22.
    _KeyBridge(
        "opentelemetry.context",
        "_SUPPRESS_HTTP_INSTRUMENTATION_KEY",
        agent_context._SUPPRESS_HTTP_INSTRUMENTATION_KEY,
        _no_converters,
    ),
)


@dataclass(frozen=True)
class _KeyTable:
    pending: tuple[_KeyBridge, ...]
    """Keys the application's API hasn't defined yet."""
    to_app: Mapping[str, tuple[str, _Convert]]
    """Vendored key → the application's key and the value converter."""
    to_agent: Mapping[str, tuple[str, _Convert]]
    """The application's key → vendored key and the value converter."""


_key_table = _KeyTable(pending=_KEY_BRIDGES, to_app={}, to_agent={})


def _keys() -> _KeyTable:
    """The current key table, after looking up the pending keys.

    Updates replace the table as a whole; concurrent ones compute the same table.
    """
    global _key_table  # pylint: disable=global-statement
    table = _key_table
    if not table.pending:
        return table
    found: list[tuple[_KeyBridge, str]] = []
    for bridge in table.pending:
        app_key = getattr(sys.modules.get(bridge.module), bridge.attribute, None)
        if isinstance(app_key, str):
            found.append((bridge, app_key))
    if not found:
        return table
    to_app = dict(table.to_app)
    to_agent = dict(table.to_agent)
    for bridge, app_key in found:
        to_app_value, to_agent_value = bridge.converters()
        to_app[bridge.agent_key] = (app_key, to_app_value)
        to_agent[app_key] = (bridge.agent_key, to_agent_value)
    found_bridges = {bridge for bridge, _ in found}
    table = _KeyTable(
        pending=tuple(bridge for bridge in table.pending if bridge not in found_bridges),
        to_app=to_app,
        to_agent=to_agent,
    )
    _key_table = table
    return table


def _translate(context: Mapping[str, object], keys: Mapping[str, tuple[str, _Convert]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in context.items():
        translation = keys.get(key)
        if translation is None:
            values[key] = value
        else:
            translated_key, convert = translation
            values[translated_key] = convert(value)
    return values


def to_app_context(context: Mapping[str, object]) -> Context:
    """The application's `Context` with the values of a vendored context."""
    return Context(_translate(context, _keys().to_app))


def to_agent_context(context: Mapping[str, object]) -> AgentContext:
    """The vendored `Context` with the values of an application's context."""
    return AgentContext(_translate(context, _keys().to_agent))


class BridgeRuntimeContext(_RuntimeContext):
    """The application's runtime context: the vendored runtime context, with translated keys."""

    def __init__(self) -> None:
        release_environment_variable(OTEL_PYTHON_CONTEXT)

    def attach(self, context: Context) -> Token[Context]:
        # The token is opaque to the application's API: it's only passed back to detach().
        return cast("Token[Context]", agent_context._RUNTIME_CONTEXT.attach(to_agent_context(context)))

    def get_current(self) -> Context:
        return to_app_context(agent_context._RUNTIME_CONTEXT.get_current())

    def detach(self, token: Token[Context]) -> None:
        agent_context._RUNTIME_CONTEXT.detach(cast("Token[AgentContext]", token))
