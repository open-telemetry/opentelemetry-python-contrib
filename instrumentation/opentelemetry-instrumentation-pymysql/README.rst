OpenTelemetry PyMySQL Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-pymysql.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-pymysql/

Installation
------------

::

    pip install opentelemetry-instrumentation-pymysql


Configuration
-------------

You can configure the semantic conventions emitted by this instrumentation via the ``OTEL_SEMCONV_STABILITY_OPT_IN`` environment variable:

- ``database`` - emit the new, stable db conventions, and stop emitting the old experimental db conventions that the instrumentation emitted previously.
- ``database/dup`` - emit both the old and the stable db conventions, allowing for a seamless transition.
- ``http`` - emit the stable HTTP conventions and stop emitting the old experimental conventions.
- ``http/dup`` - emit both the old and the stable HTTP conventions during a transition period.

The environment variable accepts a comma-separated list of opt-in values. For example, ``database,http/dup`` enables stable database conventions and emits both old and stable HTTP conventions.

By default, the old experimental database and HTTP conventions are emitted.

References
----------
* `OpenTelemetry PyMySQL Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/pymysql/pymysql.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
