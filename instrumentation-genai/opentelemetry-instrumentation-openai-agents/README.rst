OpenTelemetry OpenAI Agents Instrumentation
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-openai-agents.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-openai-agents/

This library allows tracing OpenAI Agents framework requests and logging of messages made by the
`OpenAI Python API library <https://pypi.org/project/openai/>`_ when used with agent frameworks.
It also captures the duration of the operations and the number of tokens used as metrics.

Installation
------------

::

    pip install opentelemetry-instrumentation-openai-agents

Dependency note
---------------

This instrumentation integrates with the OpenAI Agents framework via the
`openai-agent <https://pypi.org/project/openai-agent/>`_ package. Ensure
``openai-agent>=0.1.0`` is installed in environments where agent events are
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
-------------

The following environment variables can be used to configure the instrumentation:

- ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT``: Set to ``true`` to capture the content of the requests and responses. Default is ``false``.
- ``OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS``: Set to ``true`` to capture metrics. Default is ``true``.

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenAI Python API Library <https://pypi.org/project/openai/>`_
