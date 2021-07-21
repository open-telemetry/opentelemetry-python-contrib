oxeye_opentelemetry OT Trace Propagator
=================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/oxeye_opentelemetry-propagator-ot-trace.svg
   :target: https://pypi.org/project/oxeye_opentelemetry-propagator-ot-trace/

Installation
------------

::

    pip install oxeye_opentelemetry-propagator-ot-trace

.. _oxeye_opentelemetry: https://github.com/ox-eye/oxeye_opentelemetry-python/

OTTrace Format
--------------

So far there is no "formal" specification of the OTTrace format. The best
document that servers this purpose that exists now is this_ implementation.

.. _this: https://github.com/opentracing/basictracer-python/blob/master/basictracer/text_propagator.py

===================== ======================================================================================================================================= =====================
Header Name           Description                                                                                                                             Required
===================== ======================================================================================================================================= =====================
``ot-tracer-traceid`` uint64 encoded as a string of 16 hex characters                                                                                         yes
``ot-tracer-spanid``  uint64 encoded as a string of 16 hex characters                                                                                         yes
``ot-tracer-sampled`` boolean encoded as a string with the values ``true`` or ``false``                                                                       no
``ot-baggage-*``      repeated string to string key-value baggage items; keys are prefixed with ``ot-baggage-`` and the corresponding value is the raw string if baggage is present
===================== ======================================================================================================================================= =====================

Interop and trace ids
---------------------

The OT Trace propagation format expects trace ids to be 64-bits. In order to
interop with oxeye_opentelemetry, trace ids need to be truncated to 64-bits before
sending them on the wire. When truncating, the least significant (right-most)
bits MUST be retained. For example, a trace id of
``3c3039f4d78d5c02ee8e3e41b17ce105`` would be truncated to
``ee8e3e41b17ce105``.

References
----------

* `oxeye_opentelemetry Project <https://oxeye_opentelemetry.io/>`_
