OpenTelemetry gRPC Integration
==============================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-grpc.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-grpc/

Client and server interceptors for `gRPC Python`_.

.. _gRPC Python: https://grpc.github.io/grpc/python/grpc.html

Installation
------------

::

     pip install opentelemetry-instrumentation-grpc


grpc metric types
-----------------

* `rpc.server.call.duration` (seconds) - Duration of incoming RPCs, recorded by the server interceptors
* `rpc.client.call.duration` (seconds) - Duration of outgoing RPCs, recorded by the client interceptors

Both metrics have the `rpc.system.name` (`grpc`), `rpc.method` (`package.Service/Method`),
`rpc.response.status_code` (gRPC status name, e.g. `OK`) and `error.type` (the gRPC status
name for failed calls, `None` otherwise) attributes.


References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_