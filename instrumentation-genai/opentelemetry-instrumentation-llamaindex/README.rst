OpenTelemetry LlamaIndex Instrumentation
========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-llamaindex.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-llamaindex/

This library allows tracing tool executions made through the
`LlamaIndex Python library <https://pypi.org/project/llama-index-core/>`_.

The emitted telemetry follows the standard OpenTelemetry
`GenAI semantic conventions <https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai>`_
(``gen_ai.*``). Tool executions are recorded as ``execute_tool`` spans.

Installation
------------

If your application is already instrumented with OpenTelemetry, add this
package to your requirements.
::

    pip install opentelemetry-instrumentation-llamaindex

Usage
-----

This section describes how to set up LlamaIndex instrumentation if you're
setting OpenTelemetry up manually.

Instrumenting tool executions
*****************************

When using the instrumentor, calls to ``FunctionTool.call`` and
``FunctionTool.acall`` will automatically emit ``execute_tool`` spans.

.. code-block:: python

    from llama_index.core.tools import FunctionTool
    from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor

    LlamaIndexInstrumentor().instrument()

    def multiply(a: int, b: int) -> int:
        return a * b

    tool = FunctionTool.from_defaults(fn=multiply, name="multiply")
    tool.call(3, 4)

Scope
*****

This instrumentation focuses on tool execution. It wraps
``llama_index.core.tools.FunctionTool.call`` (sync) and ``FunctionTool.acall``
(async). It intentionally does not wrap LLM, retriever, or workflow classes to
avoid double-instrumentation with dedicated provider instrumentations. Broader
LlamaIndex coverage is deferred as a follow-up.

Enabling the latest experimental features
***********************************************

This instrumentation emits telemetry exclusively through the latest
experimental GenAI semantic conventions. To enable it, set the environment
variable ``OTEL_SEMCONV_STABILITY_OPT_IN`` to ``gen_ai_latest_experimental``.
Or, if you use ``OTEL_SEMCONV_STABILITY_OPT_IN`` to enable other features,
append ``,gen_ai_latest_experimental`` to its value.

.. note:: Generative AI semantic conventions are still evolving. The latest experimental features will introduce breaking changes in future releases.

Enabling message content
*************************

Tool arguments and return values are not captured by default. To capture this
content, set the environment variable
``OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`` to one of the following
values:

- ``span_only`` - capture content on *span* attributes.
- ``event_only`` - capture content on *event* attributes.
- ``span_and_event`` - capture content on both *span* and *event* attributes.

Uninstrument
************

To uninstrument clients, call the uninstrument method:

.. code-block:: python

    from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor

    LlamaIndexInstrumentor().instrument()
    # ...

    # Uninstrument
    LlamaIndexInstrumentor().uninstrument()

References
----------
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `LlamaIndex Python library <https://pypi.org/project/llama-index-core/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
