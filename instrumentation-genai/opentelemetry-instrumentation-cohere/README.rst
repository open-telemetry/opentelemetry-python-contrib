OpenTelemetry Cohere Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-cohere.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-cohere/

This library allows tracing applications that use the `Cohere Python SDK <https://pypi.org/project/cohere/>`_.

Installation
------------

::

    pip install opentelemetry-instrumentation-cohere

Usage
-----

.. code-block:: python

    from cohere import ClientV2
    from opentelemetry.instrumentation.cohere import CohereInstrumentor

    CohereInstrumentor().instrument()

    client = ClientV2()
    response = client.chat(
        model="command-r-plus",
        messages=[
            {"role": "user", "content": "Hello, how are you?"},
        ],
    )

References
----------

* `OpenTelemetry Cohere Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/cohere/cohere.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
