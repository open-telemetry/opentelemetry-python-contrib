oxeye_opentelemetry Requests Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-instrumentation-requests.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-instrumentation-requests/

This library allows tracing HTTP requests made by the
`requests <https://requests.readthedocs.io/en/master/>`_ library.

Installation
------------

::

     pip install oxeye_opentelemetry-instrumentation-requests
     
Configuration
-------------

.. code-block:: python

     from oxeye_opentelemetry.instrumentation.requests import RequestsInstrumentor
     RequestsInstrumentor().instrument()


References
----------

* `oxeye_opentelemetry requests Instrumentation <https://oxeye_opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/requests/requests.html>`_
* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
* `oxeye_opentelemetry Python Examples <https://github.com/ox-eye/oxeye_opentelemetry-python/tree/main/docs/examples>`_
