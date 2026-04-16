OpenTelemetry vLLM Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-vllm.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-vllm/

This library provides **server-side** OpenTelemetry instrumentation for
`vLLM <https://pypi.org/project/vllm/>`_, the popular open-source LLM
inference engine. Unlike other GenAI instrumentations that are client-side,
this instrumentation hooks directly into the vLLM engine to capture
server-side metrics.

Key metrics
-----------

* ``gen_ai.server.time_to_first_token`` — Time to generate the first token (TTFT)
* ``gen_ai.server.time_per_output_token`` — Time per output token (TPOT)
* ``gen_ai.server.request.duration`` — End-to-end request duration on the server
* ``gen_ai.client.operation.duration`` — Operation duration
* ``gen_ai.client.token.usage`` — Input and output token counts

Installation
------------

::

    pip install opentelemetry-instrumentation-vllm

Note: ``vllm`` itself is an optional dependency since it requires GPU
hardware. The package installs without it and fails gracefully at
instrument time if vLLM is not available.

Usage
-----

.. code-block:: python

    from vllm import LLM, SamplingParams
    from opentelemetry.instrumentation.vllm import VLLMInstrumentor

    # Instrument before creating the LLM instance
    VLLMInstrumentor().instrument()

    llm = LLM(model="meta-llama/Llama-2-7b-hf")
    sampling_params = SamplingParams(temperature=0.8, max_tokens=256)
    outputs = llm.generate(["Hello, world!"], sampling_params)

Chat completions
****************

.. code-block:: python

    VLLMInstrumentor().instrument()

    llm = LLM(model="meta-llama/Llama-2-7b-chat-hf")
    messages = [{"role": "user", "content": "What is OpenTelemetry?"}]
    outputs = llm.chat(messages)

Uninstrument
************

.. code-block:: python

    from opentelemetry.instrumentation.vllm import VLLMInstrumentor

    VLLMInstrumentor().instrument()
    # ...
    VLLMInstrumentor().uninstrument()

References
----------
* `vLLM Project <https://github.com/vllm-project/vllm>`_
* `OpenTelemetry GenAI Semantic Conventions <https://opentelemetry.io/docs/specs/semconv/gen-ai/>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
