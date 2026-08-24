OpenTelemetry OracleDB Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-oracledb.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-oracledb/

This library provides tracing for the `python-oracledb`_ database driver. It
instruments synchronous and asynchronous connections and emits client spans
for cursor ``execute``, ``executemany``, and ``callproc`` operations.

Installation
------------

::

    pip install opentelemetry-instrumentation-oracledb

Usage
-----

Enable instrumentation before creating connections:

.. code-block:: python

    import oracledb

    from opentelemetry.instrumentation.oracledb import OracleDBInstrumentor

    OracleDBInstrumentor().instrument()

    connection = oracledb.connect(
        user="system",
        password="password",
        dsn="localhost:1521/FREEPDB1",
    )

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM dual")

Existing synchronous connections can be instrumented explicitly:

.. code-block:: python

    connection = OracleDBInstrumentor().instrument_connection(connection)

The ``opentelemetry_instrumentor`` entry point also enables discovery by the
``opentelemetry-instrument`` command.

References
----------

* `OpenTelemetry OracleDB Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/oracledb/oracledb.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `python-oracledb`_

.. _python-oracledb: https://python-oracledb.readthedocs.io/
