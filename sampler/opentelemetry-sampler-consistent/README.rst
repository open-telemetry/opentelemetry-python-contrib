OpenTelemetry Consistent Sampler
==========================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-sampler-consistent.svg
   :target: https://pypi.org/project/opentelemetry-sampler-consistent/

This library contains OpenTelemetry `Consistent Samplers <https://opentelemetry.io/docs/specs/otel/trace/tracestate-probability-sampling/>`_
which allow backends to derive signals such as metrics from sampled traces.

Installation
------------

::

    pip install opentelemetry-sampler-consistent

---------------------------

Usage example for ``opentelemetry-sampler-consistent``

.. code-block:: python

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sampler.consistent import parent_based, probability_based


    trace.set_tracer_provider(
        TracerProvider(
            sampler=parent_based(probability_based(0.5)),
        )
    )

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_