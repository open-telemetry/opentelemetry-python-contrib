OpenTelemetry Cohere Instrumentation
=====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-cohere.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-cohere/

This library provides instrumentation for applications that use the `Cohere Python SDK <https://pypi.org/project/cohere/>`_.

.. note::
    This package is currently a scaffold. Chat completions instrumentation
    will be added in a follow-up PR. Installing and calling ``instrument()``
    is safe but will not produce spans or logs until then.

Installation
------------

::

    pip install opentelemetry-instrumentation-cohere

Usage
-----

.. code-block:: python

    from opentelemetry.instrumentation.cohere import CohereInstrumentor

    CohereInstrumentor().instrument()

    # Chat completions patching will be wired up in a follow-up PR.
    # Once that lands, Cohere SDK calls will automatically produce
    # traces and logs.


References
----------

* `OpenTelemetry Cohere Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/cohere/cohere.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_
