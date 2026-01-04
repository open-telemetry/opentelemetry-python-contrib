OpenTelemetry LlamaIndex Instrumentation
========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-llamaindex.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-llamaindex/

This library allows tracing requests made by the LlamaIndex library.

Installation
------------

::

    pip install opentelemetry-instrumentation-llamaindex

References
----------

* `OpenTelemetry LlamaIndex Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/llamaindex/llamaindex.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `LlamaIndex <https://www.llamaindex.ai/>`_

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.llamaindex import LlamaIndexInstrumentor
    from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

    # Instrument LlamaIndex
    LlamaIndexInstrumentor().instrument()

    # Load documents and create index
    documents = SimpleDirectoryReader('data').load_data()
    index = VectorStoreIndex.from_documents(documents)

    # Query the index
    query_engine = index.as_query_engine()
    response = query_engine.query("What is the document about?")

    print(response)

Configuration
-------------

Content Capture
~~~~~~~~~~~~~~~

By default, message content is not captured. To enable content capture, set the
environment variable:

.. code-block:: bash

    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true

Instrumented Operations
-----------------------

The instrumentation automatically traces the following LlamaIndex operations:

Query Operations
~~~~~~~~~~~~~~~~

* Query engine executions
* Retriever operations (retrieve, aretrieve)
* Synthesizer operations (synthesize, asynthesize)

Embedding Operations
~~~~~~~~~~~~~~~~~~~~

* Text embedding generation
* Query embedding generation
* Batch embedding operations

Agent Operations
~~~~~~~~~~~~~~~~

* Agent runner chat/achat operations
* Tool calls and executions

Pipeline Operations
~~~~~~~~~~~~~~~~~~~

* Query pipeline executions
* Multi-step workflows

Span Hierarchy
--------------

The instrumentation creates spans that follow LlamaIndex's execution flow::

    query_engine.query
    ├── retriever.retrieve
    │   └── embedding.get_query_embedding
    └── synthesizer.synthesize
        └── llm.chat (captured by LLM instrumentation)

For agent workflows::

    agent.chat
    ├── tool.call
    └── llm.chat (captured by LLM instrumentation)

Attributes
----------

All custom attributes follow the ``gen_ai.llamaindex.*`` namespace:

Operation Attributes
~~~~~~~~~~~~~~~~~~~~

* ``gen_ai.operation.name`` - Type of operation (workflow, task, agent, execute_tool, embeddings)
* ``gen_ai.llamaindex.entity.name`` - Name of the LlamaIndex component
* ``gen_ai.llamaindex.entity.input`` - Input to the operation (when content capture enabled)
* ``gen_ai.llamaindex.entity.output`` - Output from the operation (when content capture enabled)

Retriever Attributes
~~~~~~~~~~~~~~~~~~~~

* ``gen_ai.llamaindex.retriever.type`` - Type of retriever used
* ``gen_ai.llamaindex.retriever.top_k`` - Number of documents to retrieve

Embedding Attributes
~~~~~~~~~~~~~~~~~~~~

* ``gen_ai.llamaindex.embedding.model`` - Embedding model name
* ``gen_ai.llamaindex.embedding.dimensions`` - Embedding dimensions

Agent Attributes
~~~~~~~~~~~~~~~~

* ``gen_ai.llamaindex.agent.type`` - Type of agent
* ``gen_ai.llamaindex.tool.name`` - Tool name being executed

Metrics
-------

The instrumentation records the following metrics:

* ``gen_ai.client.operation.duration`` - Duration of GenAI operations (seconds)
* ``gen_ai.client.token.usage`` - Number of tokens used (when available)

Streaming Support
-----------------

The instrumentation supports streaming responses. When streaming is enabled,
the span is kept open until the stream is fully consumed, at which point
final metrics and output attributes are recorded.

Requirements
------------

* LlamaIndex 0.10.0 or higher (llama-index-core)
* Python 3.9 or higher

The instrumentation uses LlamaIndex's native dispatcher pattern (available in
0.10.20+) for automatic instrumentation of all components.

API
---
