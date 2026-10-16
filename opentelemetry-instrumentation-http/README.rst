OpenTelemetry HTTP Instrumentation
==================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-http.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-http/

Shared base for OpenTelemetry HTTP instrumentations.

Installation
------------

::

    pip install opentelemetry-instrumentation-http

Stability
---------

The APIs in ``opentelemetry.instrumentation.http.client``, including
``HttpClientTelemetryOptions``, and the environment variables in
``opentelemetry.instrumentation.http.environment_variables`` follow
semantic versioning.

.. warning::
    ``opentelemetry.instrumentation.http.client._incubating``, including
    ``HttpClientTelemetryDevelopmentOptions``, the ``development_options``
    argument and the ``OTEL_INSTRUMENTATION_HTTP_CLIENT_EMIT_EXPERIMENTAL_*``
    environment variables, is at the **Development** stability level and does
    NOT follow semantic versioning. BREAKING changes may occur in any release,
    including minor and patch releases. Changelog entries for these changes are
    prefixed with ``Breaking (development):``.


References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
