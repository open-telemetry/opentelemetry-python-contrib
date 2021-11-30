OpenTelemetry Celery Instrumentation
====================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-celery.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-celery/

Instrumentation for Celery.


Installation
------------

::

    pip install opentelemetry-instrumentation-celery

References
----------
* `OpenTelemetry Celery Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/celery/celery.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `OpenTelemetry Python Examples <https://github.com/open-telemetry/opentelemetry-python/tree/main/docs/examples>`_

Note - Keeping Published Tasks Span
-----------------------------------
In the case where Celery Worker "**A**" publishes a Task ``b.ping`` to Celery Worker "**B**".

Let's say Worker "**A**" receives a Task ``a.ping`` which publishes a Task ``b.ping``
::

    ==>a.ping
       ==>b.ping

to keep the span relations, the task ``b.ping`` should be added to the Celery Worker "**A**" tasks registry.
otherwise, the process span would not reside at the original parent task Trace.

