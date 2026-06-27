# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""

Usage
-----

The OpenTelemetry ``pymemcache`` integration traces pymemcache client operations

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.pymemcache import PymemcacheInstrumentor

    PymemcacheInstrumentor().instrument()

    from pymemcache.client.base import Client
    client = Client(('localhost', 11211))
    client.set('some_key', 'some_value')

API
---
"""
# pylint: disable=no-value-for-parameter

import logging
from typing import Collection

import pymemcache
from wrapt import wrap_function_wrapper as _wrap

from opentelemetry.instrumentation._semconv import (
    _get_schema_url_for_signal_types,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _set_db_statement,
    _set_db_system,
    _set_http_net_peer_name_client,
    _set_http_peer_port_client,
    _set_net_transport,
)
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.pymemcache.package import _instruments
from opentelemetry.instrumentation.pymemcache.version import __version__
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NetTransportValues,
)
from opentelemetry.semconv.attributes.network_attributes import (
    NetworkTransportValues,
)
from opentelemetry.trace import SpanKind, get_tracer

logger = logging.getLogger(__name__)


COMMANDS = [
    "set",
    "set_many",
    "add",
    "replace",
    "append",
    "prepend",
    "cas",
    "get",
    "get_many",
    "gets",
    "gets_many",
    "delete",
    "delete_many",
    "incr",
    "decr",
    "touch",
    "stats",
    "version",
    "flush_all",
    "quit",
    "set_multi",
    "get_multi",
]


def _set_connection_attributes(span, instance, sem_conv_opt_in_mode):
    if not span.is_recording():
        return
    for key, value in _get_address_attributes(
        instance, sem_conv_opt_in_mode
    ).items():
        span.set_attribute(key, value)


def _with_tracer_wrapper(func):
    """Helper for providing tracer for wrapper functions."""

    def _with_tracer(tracer, cmd, sem_conv_opt_in_mode):
        def wrapper(wrapped, instance, args, kwargs):
            # prevent double wrapping
            if hasattr(wrapped, "__wrapped__"):
                return wrapped(*args, **kwargs)

            return func(tracer, cmd, sem_conv_opt_in_mode, wrapped, instance, args, kwargs)

        return wrapper

    return _with_tracer


@_with_tracer_wrapper
def _wrap_cmd(tracer, cmd, sem_conv_opt_in_mode, wrapped, instance, args, kwargs):
    with tracer.start_as_current_span(
        cmd, kind=SpanKind.CLIENT, attributes={}
    ) as span:
        try:
            if span.is_recording():
                if not args:
                    vals = ""
                else:
                    vals = _get_query_string(args[0])

                query = f"{cmd}{' ' if vals else ''}{vals}"

                stmt_attrs = {}
                _set_db_statement(stmt_attrs, query, sem_conv_opt_in_mode)
                for k, v in stmt_attrs.items():
                    span.set_attribute(k, v)

                _set_connection_attributes(span, instance, sem_conv_opt_in_mode)
        except Exception as ex:  # pylint: disable=broad-except
            logger.warning(
                "Failed to set attributes for pymemcache span %s", str(ex)
            )

        return wrapped(*args, **kwargs)


def _get_query_string(arg):
    """Return the query values given the first argument to a pymemcache command.

    If there are multiple query values, they are joined together
    space-separated.
    """
    keys = ""

    if isinstance(arg, dict):
        arg = list(arg)

    if isinstance(arg, str):
        keys = arg
    elif isinstance(arg, bytes):
        keys = arg.decode()
    elif isinstance(arg, list) and len(arg) >= 1:
        if isinstance(arg[0], str):
            keys = " ".join(arg)
        elif isinstance(arg[0], bytes):
            keys = b" ".join(arg).decode()

    return keys


def _get_address_attributes(instance, sem_conv_opt_in_mode):
    """Attempt to get host and port from Client instance."""
    address_attributes = {}

    _set_db_system(address_attributes, "memcached", sem_conv_opt_in_mode)

    if hasattr(instance, "server"):
        if isinstance(instance.server, tuple):
            host, port = instance.server
            _set_http_net_peer_name_client(address_attributes, host, sem_conv_opt_in_mode)
            _set_http_peer_port_client(address_attributes, port, sem_conv_opt_in_mode)
            _set_net_transport(address_attributes, NetTransportValues.IP_TCP.value, NetworkTransportValues.TCP.value, sem_conv_opt_in_mode)
        elif isinstance(instance.server, str):
            _set_http_net_peer_name_client(address_attributes, instance.server, sem_conv_opt_in_mode)
            _set_net_transport(address_attributes, NetTransportValues.OTHER.value, NetworkTransportValues.PIPE.value, sem_conv_opt_in_mode)

    return address_attributes


class PymemcacheInstrumentor(BaseInstrumentor):
    """An instrumentor for pymemcache See `BaseInstrumentor`"""

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        _OpenTelemetrySemanticConventionStability._initialize()
        sem_conv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE,
        )

        tracer_provider = kwargs.get("tracer_provider")
        tracer = get_tracer(
            __name__,
            __version__,
            tracer_provider,
            schema_url=_get_schema_url_for_signal_types(
                [_OpenTelemetryStabilitySignalType.DATABASE]
            ),
        )

        for cmd in COMMANDS:
            _wrap(
                "pymemcache.client.base",
                f"Client.{cmd}",
                _wrap_cmd(tracer, cmd, sem_conv_opt_in_mode),
            )

    def _uninstrument(self, **kwargs):
        for command in COMMANDS:
            unwrap(pymemcache.client.base.Client, f"{command}")
