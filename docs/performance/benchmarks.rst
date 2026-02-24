Performance Tests - Benchmarks
==============================

This directory contains benchmark tests for various packages in this repository.

To run benchmarks locally, look for ``benchmark`` or ``benchmarks`` directories within individual package directories. For example:

- ``propagator/opentelemetry-propagator-aws-xray/benchmarks/``
- ``sdk-extension/opentelemetry-sdk-extension-aws/benchmarks/``

Run benchmarks using pytest with the ``--benchmark-only`` flag after installing ``pytest-benchmark``:

.. code-block:: sh

    pip install pytest-benchmark
    pytest --benchmark-only path/to/benchmarks/

Note: Pre-built benchmark results are not currently hosted online.
