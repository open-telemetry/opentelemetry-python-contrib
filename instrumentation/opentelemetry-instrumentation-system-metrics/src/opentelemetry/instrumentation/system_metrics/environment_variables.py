# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

OTEL_PYTHON_SYSTEM_METRICS_EXCLUDED_METRICS = (
    "OTEL_PYTHON_SYSTEM_METRICS_EXCLUDED_METRICS"
)
"""
.. envvar:: OTEL_PYTHON_SYSTEM_METRICS_EXCLUDED_METRICS

Specifies which system and process metrics should be excluded from collection
when using the default configuration. The value should be provided as a
comma separated list of glob patterns that match metric names to exclude.

**Example Usage:**

To exclude all CPU related metrics and specific process metrics:

.. code:: bash

    export OTEL_PYTHON_SYSTEM_METRICS_EXCLUDED_METRICS="system.cpu.*,process.memory.*"

To exclude a specific metric:

.. code:: bash

    export OTEL_PYTHON_SYSTEM_METRICS_EXCLUDED_METRICS="system.network.io"

**Supported Glob Patterns:**

The environment variable supports standard glob patterns for metric filtering:

- ``*`` - Matches any sequence of characters within a metric name

**Example Patterns:**

- ``system.*`` - Exclude all system metrics
- ``process.cpu.*`` - Exclude all process CPU related metrics
- ``*.utilization`` - Exclude all utilization metrics
- ``system.memory.usage`` - Exclude the system memory usage metric

"""
