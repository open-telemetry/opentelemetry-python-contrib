OpenTelemetry AWS Bedrock Instrumentation
=========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-bedrock.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-bedrock/

This library allows tracing LLM requests made against
`AWS Bedrock <https://aws.amazon.com/bedrock/>`_ through the
`boto3 <https://pypi.org/project/boto3/>`_ / ``botocore`` ``bedrock-runtime``
client. It also captures the duration of the operations and the number of
tokens used as metrics.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``), using the ``aws.bedrock`` value for ``gen_ai.provider.name``.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-bedrock

Usage
-----

This section describes how to set up AWS Bedrock instrumentation if you're
setting OpenTelemetry up manually.

Instrumenting all clients
*************************

The instrumentor wraps ``botocore``'s client factory, so any
``bedrock-runtime`` client created after ``instrument()`` is called
automatically traces its ``converse`` and ``invoke_model`` calls.

Make sure to configure OpenTelemetry tracing, logging, and metrics to capture
all telemetry emitted by the instrumentation.

.. code-block:: python

    import boto3
    from opentelemetry.instrumentation.bedrock import BedrockInstrumentor

    BedrockInstrumentor().instrument()

    client = boto3.client("bedrock-runtime", region_name="us-east-1")
    response = client.converse(
        modelId="anthropic.claude-3-haiku-20240307-v1:0",
        messages=[
            {"role": "user", "content": [{"text": "Write a short poem."}]},
        ],
    )

Enabling the latest experimental features
***********************************************

This instrumentation emits telemetry exclusively through the latest
experimental GenAI semantic conventions. To enable it, set the environment
variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``.
Or, if you use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features,
append ``,gen_ai_latest_experimental`` to its value.

**Without this setting the AWS Bedrock instrumentation is a no-op** (a legacy
Semantic Conventions v1.30.0 path is not yet provided).

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Enabling message content
*************************

Message content such as the contents of the prompt and completion are not
captured by default. To capture message content, set the environment variable
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of the following
values:

- ``span_only`` - capture content on *span* attributes.
- ``event_only`` - capture content on *event* attributes.
- ``span_and_event`` - capture content on both *span* and *event* attributes.

Uploading prompts and completions
*********************************

To enable the built-in upload hook, set:

- ``OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload``
- ``OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH`` to an ``fsspec``-compatible URI/path
  (e.g. ``/path/to/prompts`` or ``gs://my_bucket``).

Install the ``upload`` extra to pull in ``fsspec``::

    pip install opentelemetry-util-genai[upload]

See the `opentelemetry-util-genai
<https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/util/opentelemetry-util-genai/README.rst>`_
for additional options.

Coverage and limitations
------------------------

The following ``bedrock-runtime`` methods are instrumented:

- ``converse`` - the unified Bedrock chat API. Request parameters, finish
  reasons, token usage, and (optionally) message content are mapped to the
  standard GenAI attributes.
- ``invoke_model`` - best-effort mapping for the Anthropic Messages body
  shape. For unrecognized bodies a span is still emitted with the request
  model and operation, but token usage and content are skipped.

Not yet covered (follow-ups):

- Streaming APIs ``converse_stream`` and ``invoke_model_with_response_stream``.
- Non-Anthropic ``invoke_model`` body shapes (Titan, Cohere, Llama, ...); these
  emit a span but no token/content attributes.
- ``aiobotocore`` async clients.

Clients that were created while instrumentation was enabled keep their wrapped
methods after ``uninstrument()`` is called; only newly created clients are
un-instrumented. This is a consequence of wrapping methods on live client
instances.

Uninstrument
************

To stop instrumenting newly created clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.bedrock import BedrockInstrumentor

    BedrockInstrumentor().instrument()
    # ...

    BedrockInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `AWS Bedrock <https://aws.amazon.com/bedrock/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
