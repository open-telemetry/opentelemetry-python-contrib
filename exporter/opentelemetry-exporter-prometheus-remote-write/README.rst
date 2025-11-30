OpenTelemetry Prometheus Remote Write Exporter
==============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-exporter-prometheus-remote-write.svg
   :target: https://pypi.org/project/opentelemetry-exporter-prometheus-remote-write/

This package contains an exporter to send metrics from the OpenTelemetry Python SDK directly to a Prometheus Remote Write integrated backend
(such as Cortex or Thanos) without having to run an instance of the Prometheus server.

Key features
------------

* Optional bounded retries with exponential backoff and jitter for retryable HTTP/network failures.


Installation
------------

::

    pip install opentelemetry-exporter-prometheus-remote-write


.. _OpenTelemetry: https://github.com/open-telemetry/opentelemetry-python/
.. _Prometheus Remote Write integrated backend: https://prometheus.io/docs/operating/integrations/

Configuration highlights
------------------------

* ``max_retries`` (default ``3``), ``retry_backoff_factor`` (default ``0.5``), ``retry_backoff_max`` (default ``5.0``), and ``retry_jitter_ratio`` (default ``0.1``) tune the retry policy for retryable statuses (429/408/5xx) and connection/timeouts.


References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `Prometheus Remote Write Integration <https://prometheus.io/docs/operating/integrations/>`_
