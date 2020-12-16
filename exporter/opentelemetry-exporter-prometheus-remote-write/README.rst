OpenTelemetry Prometheus Remote Write Exporter
=========================================================

This package contains an exporter to send `OTLP`_ metrics from the
`OpenTelemetry Python SDK`_ directly to a `Prometheus Remote Write integrated backend`_
(such as Cortex or Thanos) without having to run an instance of the
Prometheus server. The latest `types.proto`_ and `remote.proto`_
protocol buffers are used to create the WriteRequest. The image below shows the
two Prometheus exporters in the OpenTelemetry Python SDK.

Pipeline 1 illustrates the setup required for a `Prometheus "pull" exporter`_.

Pipeline 2 illustrates the setup required for the Prometheus Remote
Write exporter.

|Prometheus SDK pipelines|

The Prometheus Remote Write Exporter is a "push" based exporter and only
works with the OpenTelemetry `push controller`_. The controller
periodically collects data and passes it to the exporter. This exporter
then converts the data into `timeseries`_ and sends it to the Remote
Write integrated backend through HTTP POST requests. The metrics
collection datapath is shown below:

|controller_datapath_final|

See the ``examples`` folder for a demo usage of this exporter

Table of Contents
=================

-  `Summary`_
-  `Table of Contents`_

   -  `Installation`_
   -  `Quickstart`_
   -  `Configuring the Exporter`_
   -  `Securing the Exporter`_

      -  `Authentication`_
      -  `TLS`_

   -  `Supported Aggregators`_
   -  `Error Handling`_
   -  `Contributing`_

      -  `Design Doc`_

Installation
------------
Prerequisite
~~~~~~~~~~~~
1. Install the snappy c-library
    **DEB**: `sudo apt-get install libsnappy-dev`
    **RPM**: `sudo yum install libsnappy-devel`
    **OSX/Brew**: `brew install snappy`
    **Windows**: `pip install python_snappy-0.5-cp36-cp36m-win_amd64.whl`
2. Install python-snappy
    `pip install python-snappy`

Exporter
~~~~~~~~

-  To install from the latest PyPi release, run
   ``pip install opentelemetry-exporter-prometheus-remote-write``


Quickstart
----------

.. code:: python

   from opentelemetry import metrics
   from opentelemetry.sdk.metrics import MeterProvider
   from opentelemetry.exporter.prometheus_remote_write import (
       PrometheusRemoteWriteMetricsExporter
   )

   # Sets the global MeterProvider instance
   metrics.set_meter_provider(MeterProvider())

   # The Meter is responsible for creating and recording metrics. Each meter has a unique name, which we set as the module's name here.
   meter = metrics.get_meter(__name__)

   exporter = PrometheusRemoteWriteMetricsExporter(endpoint="endpoint_here") # add other params as needed

   metrics.get_meter_provider().start_pipeline(meter, exporter, 5)

Configuring the Exporter
------------------------

The exporter can be configured through parameters passed to the
constructor. Here are all the options:

-  ``endpoint``: url where data will be sent **(Required)**
-  ``basic_auth``: username and password for authentication
   **(Optional)**
-  ``headers``: additional headers for remote write request as
   determined by the remote write backend's API **(Optional)**
-  ``timeout``: timeout for requests to the remote write endpoint in
   seconds **(Optional)**
-  ``proxies``: dict mapping request proxy protocols to proxy urls
   **(Optional)**
-  ``tls_config``: configuration for remote write TLS settings
   **(Optional)**

Example with all the configuration options:

.. code:: python

   exporter = PrometheusRemoteWriteMetricsExporter(
       endpoint="http://localhost:9009/api/prom/push",
       timeout=30,
       basic_auth={
           "username": "user",
           "password": "pass123",
       },
       headers={
           "X-Scope-Org-ID": "5",
           "Authorization": "Bearer mytoken123",
       },
       proxies={
           "http": "http://10.10.1.10:3000",
           "https": "http://10.10.1.10:1080",
       },
       tls_config={
           "cert_file": "path/to/file",
           "key_file": "path/to/file",
           "ca_file": "path_to_file",
           "insecure_skip_verify": true, # for developing purposes
       }
   )

Securing the Exporter
---------------------

Authentication
~~~~~~~~~~~~~~

The exporter provides two forms of authentication which are shown below.
Users can add their own custom authentication by setting the appropriate
values in the ``headers`` dictionary

1. Basic Authentication Basic authentication sets a HTTP Authorization
   header containing a base64 encoded username/password pair. See `RFC
   7617`_ for more information. This

.. code:: python

   exporter = PrometheusRemoteWriteMetricsExporter(
       basic_auth={"username": "base64user",  "password": "base64pass"}
   )

2. Bearer Token Authentication This custom configuration can be achieved
   by passing in a custom ``header`` to the constructor. See `RFC 6750`_
   for more information.

.. code:: python

   header = {
       "Authorization": "Bearer mytoken123"
   }

TLS
~~~

Users can add TLS to the exporter's HTTP Client by providing certificate
and key files in the ``tls_config`` parameter.

Supported Aggregators
---------------------
Behaviour of these aggregators is outlined in the `OpenTelemetry Specification <https://github.com/open-telemetry/opentelemetry-specification/blob/master/specification/metrics/api.md#aggregations>`_.

-  Sum
-  MinMaxSumCount
-  Histogram
-  LastValue
-  ValueObserver

All aggregators are converted into the `timeseries`_ data format. However, method in
which they are converted `differs <https://github.com/open-telemetry/opentelemetry-python-contrib/blob/master/exporter/opentelemetry-exporter-prometheus-remote-write/src/opentelemetry/exporter/prometheus_remote_write/__init__.py#L196>`_ from aggregator to aggregator. A
map of the conversion methods can be found `here <https://github.com/open-telemetry/opentelemetry-python-contrib/blob/master/exporter/opentelemetry-exporter-prometheus-remote-write/src/opentelemetry/exporter/prometheus_remote_write/__init__.py#L75>`_.


Error Handling
--------------

In general, errors are raised by the calling function. The exception is
for failed requests where any error status code is logged as a warning
instead.

This is because the exporter does not implement any retry logic as data that
failed to export will be dropped.

For example, consider a situation where a user increments a Counter
instrument 5 times and an export happens between each increment. If the
exports happen like so:

::

   SUCCESS FAIL FAIL SUCCESS SUCCESS
   1       2    3    4       5

Then the received data will be:

::

   1 4 5

Contributing
------------

If you would like to learn more about the exporter's structure and
design decisions please view the design document below

Design Doc
~~~~~~~~~~

`Design Document`_

This document is stored elsewhere as it contains large images which will
significantly increase the size of this repo.

.. _Summary: #opentelemetry-python-sdk-prometheus-remote-write-exporter
.. _Table of Contents: #table-of-contents
.. _Installation: #installation
.. _Quickstart: #quickstart
.. _Configuring the Exporter: #configuring-the-exporter
.. _Securing the Exporter: #securing-the-exporter
.. _Authentication: #authentication
.. _TLS: #tls
.. _Supported Aggregators: #supported-aggregators
.. _Error Handling: #error-handling
.. _Contributing: #contributing
.. _Design Doc: #design-doc
.. |Prometheus SDK pipelines| image:: https://user-images.githubusercontent.com/20804975/100285430-e320fd80-2f3e-11eb-8217-a562c559153c.png
.. |controller_datapath_final| image:: https://user-images.githubusercontent.com/20804975/100486582-79d1f380-30d2-11eb-8d17-d3e58e5c34e9.png
.. _RFC 7617: https://tools.ietf.org/html/rfc7617
.. _RFC 6750: https://tools.ietf.org/html/rfc6750
.. _Design Document: https://github.com/open-o11y/docs/blob/master/python-prometheus-remote-write/design-doc.md
.. _OTLP: https://github.com/open-telemetry/opentelemetry-specification/blob/master/specification/protocol/otlp.md
.. _OpenTelemetry Python SDK: https://github.com/open-telemetry/opentelemetry-python
.. _Prometheus "pull" exporter: https://github.com/open-telemetry/opentelemetry-python/tree/master/exporter/opentelemetry-exporter-prometheus
.. _Prometheus Remote Write integrated backend: https://prometheus.io/docs/operating/integrations/
.. _types.proto: https://github.com/prometheus/prometheus/blob/master/prompb/types.proto
.. _remote.proto: https://github.com/prometheus/prometheus/blob/master/prompb/remote.proto
.. _push controller: https://github.com/open-telemetry/opentelemetry-python/blob/master/opentelemetry-sdk/src/opentelemetry/sdk/metrics/export/controller.py#L22
.. _timeseries: https://prometheus.io/docs/concepts/data_model/
