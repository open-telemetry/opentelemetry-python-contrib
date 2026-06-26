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
from opentelemetry.instrumentation.cassandra.package import (
    _instruments_any,
    _instruments_cassandra_driver,
    _instruments_scylla_driver,
)
from opentelemetry.instrumentation.cassandra.version import __version__
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.instrumentation.utils import unwrap
from opentelemetry.instrumentation._semconv import (
    _get_schema_url_for_signal_types,
    _OpenTelemetrySemanticConventionStability,
    _OpenTelemetryStabilitySignalType,
    _report_new,
    _report_old,
)
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_STATEMENT,
    DB_SYSTEM,
)
from opentelemetry.semconv._incubating.attributes.net_attributes import (
    NET_PEER_NAME,
)
from opentelemetry.semconv.attributes.db_attributes import (
    DB_NAMESPACE,
    DB_QUERY_TEXT,
    DB_SYSTEM_NAME,
)
from opentelemetry.semconv.attributes.server_attributes import (
    SERVER_ADDRESS,
)


def _instrument(tracer_provider, include_db_statement=False, sem_conv_opt_in_mode=None):
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
                if _report_old(sem_conv_opt_in_mode):
                    span.set_attribute(DB_NAME, instance.keyspace)
                    span.set_attribute(DB_SYSTEM, "cassandra")
                    span.set_attribute(
                        NET_PEER_NAME,
                        instance.cluster.contact_points,
                    )
                if _report_new(sem_conv_opt_in_mode):
                    span.set_attribute(DB_NAMESPACE, instance.keyspace)
                    span.set_attribute(DB_SYSTEM_NAME, "cassandra")
                    span.set_attribute(
                        SERVER_ADDRESS,
                        instance.cluster.contact_points,
                    )

                if include_db_statement:
                    query = args[0]
                    if _report_old(sem_conv_opt_in_mode):
                        span.set_attribute(DB_STATEMENT, str(query))
                    if _report_new(sem_conv_opt_in_mode):
                        span.set_attribute(DB_QUERY_TEXT, str(query))

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
