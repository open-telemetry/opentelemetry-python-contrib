OpenTelemetry OpenAI Agents Instrumentation
===========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-openai-agents.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-openai-agents/

This library instruments the `OpenAI Agents framework <https://openai.github.io/openai-agents-python/>`_
to trace requests and log messages flowing through agents. It also captures operation duration and
token usage as metrics.

Installation
------------

::

    pip install opentelemetry-instrumentation-openai-agents

Dependency note
---------------

This instrumentation integrates with the OpenAI Agents framework via the
`openai-agents <https://pypi.org/project/openai-agents/>`_ package. Ensure
``openai-agents>=0.3.2`` is installed in environments where agent events are
emitted; otherwise, the instrumentor will load but skip processor setup.

Usage
-----

.. code:: python

    from openai import OpenAI
    from opentelemetry.instrumentation.openai_agents import OpenAIAgentsInstrumentor

    OpenAIAgentsInstrumentor().instrument()

    # Your OpenAI agents code here
    client = OpenAI()

API
---

The `opentelemetry-instrumentation-openai-agents` package provides automatic instrumentation for the OpenAI Agents framework.

Configuration
--------------

This instrumentation captures content, metrics, and events by default with no additional configuration required.
If you are installing and setting up this tracing library, the assumption is you want full capture.

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenAI Python API Library <https://pypi.org/project/openai/>`_
