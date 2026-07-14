OpenTelemetry Google Cloud Resource Detector
============================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-resourcedetector-gcp.svg
   :target: https://pypi.org/project/opentelemetry-resourcedetector-gcp/

This library provides support for detecting GCP resources like GCE, GKE, etc.

Installation
------------

::

    pip install opentelemetry-resourcedetector-gcp

Usage
-----

The ``GoogleCloudResourceDetector`` is automatically used by the OpenTelemetry SDK 
when it is installed in the python environment.

If you are setting resource detectors through the environment variable ``OTEL_EXPERIMENTAL_RESOURCE_DETECTORS``, 
you should use the value ``gcp``, for the ``GoogleCloudResourceDetector`` to be installed.

References
----------

* `GCP Open Telemetry Docs <https://cloud.google.com/learn/what-is-opentelemetry>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
