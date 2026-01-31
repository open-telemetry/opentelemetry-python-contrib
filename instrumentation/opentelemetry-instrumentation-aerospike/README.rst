OpenTelemetry Aerospike Instrumentation
=======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-aerospike.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-aerospike/

This library allows tracing requests made by the Aerospike library.

Installation
------------

::

    pip install opentelemetry-instrumentation-aerospike

Requirements
------------

- Python >= 3.9
- **aerospike >= 17.0.0** (minimum supported version)

.. note::

   This instrumentation only supports aerospike Python client version 17.0.0 and above.
   Version 17.0.0 introduced significant API changes including removal of deprecated methods.

Supported Operations
--------------------

The following Aerospike client methods are instrumented:

- **Single Record Operations**: ``put``, ``get``, ``select``, ``exists``, ``remove``, ``touch``, ``operate``, ``append``, ``prepend``, ``increment``
- **Batch Operations**: ``batch_read``, ``batch_write``, ``batch_operate``, ``batch_remove``, ``batch_apply``
- **Query/Scan Operations**: ``query``, ``scan``
- **UDF Operations**: ``apply``, ``scan_apply``, ``query_apply``
- **Admin Operations**: ``truncate``, ``info_all``

Aerospike Client Version Compatibility
--------------------------------------

**Minimum Version: 17.0.0**

+----------+--------------------------------------------------+
| Version  | Changes                                          |
+==========+==================================================+
| 17.0.0   | - Removed ``get_many()``, ``exists_many()``,     |
|          |   ``select_many()`` (use ``batch_read()``)       |
|          | - Removed ``batch_get_ops()``                    |
|          |   (use ``batch_operate()``)                      |
|          | - Removed ``admin_query_user()``,                |
|          |   ``admin_query_users()``                        |
+----------+--------------------------------------------------+
| 18.0.0   | - Added ``NamespaceNotFound`` exception          |
|          | - Added ``InvalidRequest`` exception             |
|          | - ``Query.where()/select()`` raises exception    |
|          |   on duplicate calls                             |
+----------+--------------------------------------------------+

.. note::

   Methods removed in version 17.0.0 are not supported by this instrumentation.
   Use the replacement methods listed above.

Captured Attributes
-------------------

The instrumentation captures the following attributes:

**Standard Attributes:**

* ``db.system.name``: Always "aerospike".
* ``db.namespace``: Aerospike namespace.
* ``db.collection.name``: Aerospike set name.
* ``db.operation.name``: The operation being performed (e.g., "GET", "PUT", "QUERY").
* ``db.user``: The user connected to the database (if configured).
* ``server.address``: The hostname or IP address of the Aerospike node.
* ``server.port``: The port of the Aerospike node.
* ``db.operation.batch.size``: Number of keys in batch operations.

**Aerospike-Specific Attributes:**

* ``db.aerospike.key``: The record key (only if ``capture_key=True`` is enabled).
* ``db.aerospike.bins``: List of bins being written or selected (for PUT/SELECT).
* ``db.aerospike.generation``: Record generation (from GET results).
* ``db.aerospike.ttl``: Record TTL (from GET results).
* ``db.aerospike.udf.module``: UDF module name.
* ``db.aerospike.udf.function``: UDF function name.

References
----------

* `OpenTelemetry Aerospike Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/aerospike/aerospike.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Aerospike Python Client <https://github.com/aerospike/aerospike-client-python>`_
* `Aerospike Incompatible API Changes <https://aerospike.com/docs/develop/client/python/incompatible>`_
