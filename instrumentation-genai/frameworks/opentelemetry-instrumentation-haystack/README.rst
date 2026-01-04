OpenTelemetry Haystack Instrumentation
======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-haystack.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-haystack/

This library allows tracing requests made by the Haystack library.

Installation
------------

::

    pip install opentelemetry-instrumentation-haystack

References
----------

* `OpenTelemetry Haystack Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/haystack/haystack.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Haystack <https://haystack.deepset.ai/>`_

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.haystack import HaystackInstrumentor
    from haystack import Pipeline
    from haystack.components.generators import OpenAIGenerator

    # Instrument Haystack
    HaystackInstrumentor().instrument()

    # Create a simple pipeline
    pipeline = Pipeline()
    pipeline.add_component("generator", OpenAIGenerator(model="gpt-4"))

    # Run the pipeline
    result = pipeline.run({
        "generator": {
            "prompt": "What is machine learning?"
        }
    })

    print(result)

Configuration
-------------

Content Capture
~~~~~~~~~~~~~~~

By default, message content is not captured. To enable content capture, set the
environment variable:

.. code-block:: bash

    export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true

Span Hierarchy
--------------

The instrumentation creates the following span hierarchy:

::

    haystack_pipeline.workflow (Pipeline.run)
    └── haystack.openai.chat (OpenAIChatGenerator.run)
        OR
    └── haystack.openai.completion (OpenAIGenerator.run)

Attributes
----------

All custom attributes follow the ``gen_ai.haystack.*`` namespace:

Pipeline Attributes
~~~~~~~~~~~~~~~~~~~

* ``gen_ai.haystack.pipeline.name`` - Pipeline name
* ``gen_ai.haystack.entity.name`` - Entity being processed
* ``gen_ai.haystack.entity.input`` - Input data (when content capture enabled)
* ``gen_ai.haystack.entity.output`` - Output data (when content capture enabled)

Generator Attributes
~~~~~~~~~~~~~~~~~~~~

* ``gen_ai.haystack.request.type`` - Type of request (chat/completion)
* ``gen_ai.request.model`` - Model being used
* ``gen_ai.request.temperature`` - Temperature setting
* ``gen_ai.request.top_p`` - Top-p setting

Supported Components
--------------------

Currently instrumented components:

* ``Pipeline.run`` - Main pipeline execution
* ``OpenAIGenerator.run`` - OpenAI completion generator
* ``OpenAIChatGenerator.run`` - OpenAI chat generator

API
---
