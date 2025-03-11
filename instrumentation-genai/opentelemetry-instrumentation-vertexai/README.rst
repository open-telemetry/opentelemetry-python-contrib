OpenTelemetry VertexAI Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-vertexai.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-vertexai/

This library allows tracing LLM requests and logging of messages made by the
`VertexAI Python API library <https://pypi.org/project/google-cloud-aiplatform/>`_.


Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-vertexai

If you don't have an VertexAI application, yet, try our `examples <examples>`_.

Check out `zero-code example <examples/zero-code>`_ for a quick start.

Usage
-----

This section describes how to set up VertexAI instrumentation if you're setting OpenTelemetry up manually.
Check out the `manual example <examples/manual>`_ for more details.

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace VertexAI chat completion operations.
You can also optionally capture prompts and completions as log events.

Make sure to configure OpenTelemetry tracing, logging, and events to capture all telemetry emitted by the instrumentation.

.. code-block:: python

    from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
    from vertexai.generative_models import GenerativeModel

    VertexAIInstrumentor().instrument()


    vertexai.init()
    model = GenerativeModel("gemini-1.5-flash-002")
    response = model.generate_content("Write a short poem on OpenTelemetry.")

Enabling message content
*************************

Message content such as the contents of the prompt, completion, function arguments and return values
are not captured by default. To capture message content as log events, set the environment variable
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to `true`.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor

    VertexAIInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    VertexAIInstrumentor().uninstrument()

References
----------
* `OpenTelemetry VertexAI Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/vertexai/vertexai.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_

