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

If you don't have a Cohere application yet, try our `examples <examples>`_
which only need a valid Cohere API key.

Check out the `zero-code example <examples/zero-code>`_ for a quick start.

Usage
-----

This section describes how to set up Cohere instrumentation if you're setting OpenTelemetry up manually.
Check out the `manual example <examples/manual>`_ for more details.

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


Configuration
-------------

Capture Message Content
***********************

By default, prompts and completions are not captured once chat instrumentation
is added. To enable message content capture, set the environment variable:

::

    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true

Note: This setting has no effect until chat completions support is added
in a follow-up PR.


References
----------

* `OpenTelemetry Cohere Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/cohere/cohere.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
