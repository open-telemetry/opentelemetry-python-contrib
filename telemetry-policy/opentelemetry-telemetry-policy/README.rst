OpenTelemetry Telemetry Policy
==============================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-telemetry-policy.svg
   :target: https://pypi.org/project/opentelemetry-telemetry-policy/

Experimental implementation of the telemetry policy concept proposed in
`OTEP 4738 <https://github.com/open-telemetry/opentelemetry-specification/blob/main/oteps/4738-telemetry-policy.md>`_. 

The only policy target implemented today is trace sampling, applied through
a runtime-swappable sampler. Policies are supplied by a local file provider
or by an OpAMP server's remote config (via ``opentelemetry-opamp-client``).

The API is not finalized; breaking changes can happen on any release.

Installation
------------

::

    pip install opentelemetry-telemetry-policy

For the OpAMP policy provider::

    pip install opentelemetry-telemetry-policy[opamp]

Usage with auto-instrumentation
-------------------------------

::

    export OTEL_TRACES_SAMPLER=telemetry_policy
    # policies from a local file, polled for changes
    export OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE=/etc/otel/policies.json
    # and/or policies from an OpAMP server's remote config
    export OTEL_PYTHON_EXPERIMENTAL_OPAMP_ENDPOINT=http://localhost:4320/v1/opamp
    opentelemetry-instrument python app.py

``OTEL_TRACES_SAMPLER_ARG`` optionally sets the fallback sampling
probability (0-1) for spans no policy matches.

References
----------

* `OpenTelemetry Project <https://opentelemetry.io/>`_
