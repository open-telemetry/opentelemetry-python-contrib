# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Cassandra instrumentation supporting `cassandra-driver`_ and `scylla-driver`_, it can be enabled by
using ``CassandraInstrumentor``.

.. _cassandra-driver: https://pypi.org/project/cassandra-driver/
.. _scylla-driver: https://pypi.org/project/scylla-driver/

Usage
-----

.. code:: python

    import cassandra.cluster
    from opentelemetry.instrumentation.cassandra import CassandraInstrumentor

    CassandraInstrumentor().instrument()

    cluster = cassandra.cluster.Cluster()
    session = cluster.connect()
    rows = session.execute("SELECT * FROM test")

API
---
"""

from importlib.metadata import PackageNotFoundError, distribution
from typing import Collection

import cassandra.cluster
from wrapt import wrap_function_wrapper

from opentelemetry import trace
from opentelemetry.instrumentation._semconv import (
    _get_schema_url_for_signal_types,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _set_db_name,
    _set_db_statement,
    _set_db_system,
    _set_http_net_peer_name_client,
)
from opentelemetry.instrumentation.cassandra.package import (
    _instruments_any,
    _instruments_cassandra_driver,
    _instruments_scylla_driver,
)
from opentelemetry.instrumentation.cassandra.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap


def _instrument(
    tracer_provider, include_db_statement=False, sem_conv_opt_in_mode=None
):
    """Instruments the cassandra-driver/scylla-driver module

    Wraps cassandra.cluster.Session.execute_async().
    """
    tracer = trace.get_tracer(
        __name__,
        __version__,
        tracer_provider,
        schema_url=_get_schema_url_for_signal_types(
            [_OpenTelemetryStabilitySignalType.DATABASE]
        ),
    )
    name = "Cassandra"

    def _traced_execute_async(func, instance, args, kwargs):
        with tracer.start_as_current_span(
            name, kind=trace.SpanKind.CLIENT
        ) as span:
            if span.is_recording():
                attrs = {}
                _set_db_system(attrs, "cassandra", sem_conv_opt_in_mode)
                _set_db_name(attrs, instance.keyspace, sem_conv_opt_in_mode)
                _set_http_net_peer_name_client(
                    attrs,
                    instance.cluster.contact_points,
                    sem_conv_opt_in_mode,
                )
                if include_db_statement:
                    query = args[0]
                    _set_db_statement(attrs, str(query), sem_conv_opt_in_mode)
                span.set_attributes(attrs)
            response = func(*args, **kwargs)
            return response

    wrap_function_wrapper(
        "cassandra.cluster", "Session.execute_async", _traced_execute_async
    )


class CassandraInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        # Determine which package of cassandra is installed.
        # Right now there are two packages, cassandra-driver and scylla-driver.
        # The latter is a fork with additional support for ScyllaDB.
        try:
            distribution("cassandra-driver")
            return (_instruments_cassandra_driver,)
        except PackageNotFoundError:
            pass

        try:
            distribution("scylla-driver")
            return (_instruments_scylla_driver,)
        except PackageNotFoundError:
            pass

        return _instruments_any

    def _instrument(self, **kwargs):
        _OpenTelemetrySemanticConventionStability._initialize()
        sem_conv_opt_in_mode = _OpenTelemetrySemanticConventionStability._get_opentelemetry_stability_opt_in_mode(
            _OpenTelemetryStabilitySignalType.DATABASE,
        )
        _instrument(
            tracer_provider=kwargs.get("tracer_provider"),
            include_db_statement=kwargs.get("include_db_statement"),
            sem_conv_opt_in_mode=sem_conv_opt_in_mode,
        )

    def _uninstrument(self, **kwargs):
        unwrap(cassandra.cluster.Session, "execute_async")
