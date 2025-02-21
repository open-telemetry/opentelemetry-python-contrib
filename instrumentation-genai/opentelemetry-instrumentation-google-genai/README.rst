OpenTelemetry Google GenAI SDK Instrumentation
==============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-google-genai.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-google-genai/

This library adds instrumentation to the `Google GenAI SDK library <https://pypi.org/project/google-genai/>`_
to emit telemetry data following `Semantic Conventions for GenAI systems <https://opentelemetry.io/docs/specs/semconv/gen-ai/>`_. 
It adds trace spans for GenAI operations, events/logs for recording prompts/responses, and emits metrics that describe the
GenAI operations in aggregate.


Experimental
------------

This package is still experimental. The instrumentation may not be complete or correct just yet.

Please see "TODOS.md" for a list of known defects/TODOs that are blockers to package stability.


Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-google-genai

If you don't have a Google GenAI SDK application, yet, try our `examples <examples>`_.

Check out `zero-code example <examples/zero-code>`_ for a quick start.

Usage
-----

This section describes how to set up Google GenAI SDK instrumentation if you're setting OpenTelemetry up manually.
Check out the `manual example <examples/manual>`_ for more details.

Instrumenting all clients
*************************

When using the instrumentor, all clients will automatically trace GenAI `generate_content` operations.
You can also optionally capture prompts and responses as log events.

Make sure to configure OpenTelemetry tracing, logging, metrics, and events to capture all telemetry emitted by the instrumentation.

.. code-block:: python

    from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
    from google.genai import Client

    GoogleGenAiSdkInstrumentor().instrument()


    client = Client()
    response = client.models.generate_content(
        model="gemini-1.5-flash-002",
        contents="Write a short poem on OpenTelemetry.")

Enabling message content
*************************

Message content such as the contents of the prompt and response
are not captured by default. To capture message content as log events, set the environment variable
`OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` to `true`.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor

    GoogleGenAiSdkInstrumentor().instrument()
    # ...

    # Uninstrument all clients
    GoogleGenAiSdkInstrumentor().uninstrument()

References
----------
* `Google Gen AI SDK Documentation <https://ai.google.dev/gemini-api/docs/sdks>`_
* `Google Gen AI SDK on GitHub <https://github.com/googleapis/python-genai>`_
* `Using Vertex AI with Google Gen AI SDK <https://cloud.google.com/vertex-ai/generative-ai/docs/sdks/overview>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_

