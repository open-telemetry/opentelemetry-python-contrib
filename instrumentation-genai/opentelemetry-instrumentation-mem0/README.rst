OpenTelemetry Mem0 Instrumentation
===================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-mem0.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-mem0/

This library allows tracing Mem0 memory operations (add, search, update,
delete) using OpenTelemetry, emitting spans with GenAI memory semantic
convention attributes.

Installation
------------

::

    pip install opentelemetry-instrumentation-mem0

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.mem0 import Mem0Instrumentor
    from mem0 import Memory

    Mem0Instrumentor().instrument()

    m = Memory()
    m.add("I prefer dark mode", user_id="alice")
    results = m.search("preferences", user_id="alice")

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Mem0 <https://github.com/mem0ai/mem0>`_
* `GenAI Memory Semantic Conventions <https://github.com/open-telemetry/semantic-conventions/pull/3250>`_
