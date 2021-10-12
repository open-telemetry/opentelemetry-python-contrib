OpenTelemetry elasticsearch Integration
========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-elasticsearch.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-elasticsearch/

This library allows tracing elasticsearch made by the
`elasticsearch <https://elasticsearch-py.readthedocs.io/en/master/>`_ library.

Installation
------------

::

     pip install opentelemetry-instrumentation-elasticsearch

Configuration
-------------

Request/Response hooks
**********************

Utilize request/reponse hooks to execute custom logic to be performed before/after performing a request.

.. code-block:: python

   def request_hook(span: Span, method: str, url: str, kwargs):
      if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_request_hook", "some-value")

   def response_hook(span: Span, response: dict):
        if span and span.is_recording():
            span.set_attribute("custom_user_attribute_from_response_hook", "some-value")

   ElasticsearchInstrumentor().instrument(request_hook=request_hook, response_hook=response_hook) 

References
----------

* `OpenTelemetry elasticsearch Integration <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/elasticsearch/elasticsearch.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
