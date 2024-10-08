OpenTelemetry karapace Instrumentation
=============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-karapace.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-karapace/

This library allows tracing requests made by karapace.

Installation
------------

::

    pip install opentelemetry-instrumentation-karapace
    pip install opentelemetry-distro
    
    in pyproject.toml: "opentelemetry-distro", # IMPORTANT without this the default configuration is missing and nothing is exported
    to facilitat auto-isntrumentation PYTHONPATH must start with opentelemetry/instrumentation/auto-isntrumentation/


::python
    add to main():     KarapaceInstrumentor().instrument() 

References
----------

* `OpenTelemetry karapace/ Tracing <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/karapace/karapace.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
