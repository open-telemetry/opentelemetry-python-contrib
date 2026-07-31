# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
OpenTelemetry Labeler
=====================

The labeler utility provides a way to add custom attributes to metrics.

This was inspired by OpenTelemetry Go's net/http instrumentation Labeler
https://github.com/open-telemetry/opentelemetry-go-contrib/pull/306

Usage
-----

The labeler is typically used within the context of an instrumented request
or operation. Use ``get_labeler`` to obtain a labeler instance for the
current context, then add attributes using the ``add`` or
``add_attributes`` methods.

Example
-------

Here's a framework-agnostic example showing manual use of the labeler:

.. code-block:: python

    from opentelemetry.instrumentation._labeler import (
        enrich_metric_attributes,
        get_labeler,
    )
    from opentelemetry.metrics import get_meter

    meter = get_meter("example.manual")
    duration_histogram = meter.create_histogram(
        name="http.server.request.duration",
        unit="s",
        description="Duration of HTTP server requests.",
    )

    def record_request(user_id: str, duration_s: float) -> None:
        labeler = get_labeler()
        labeler.add("user_id", user_id)
        labeler.add_attributes(
            {
                "has_premium": user_id in ["123", "456"],
                "experiment_group": "control",
                "feature_enabled": True,
                "user_segment": "active",
            }
        )

        base_attributes = {
            "http.request.method": "GET",
            "http.response.status_code": 200,
        }
        duration_histogram.record(
            max(duration_s, 0),
            enrich_metric_attributes(base_attributes),
        )

This package introduces the shared Labeler API and helper utilities.
Framework-specific integration points that call
``enrich_metric_attributes`` (for example before ``Histogram.record``)
can be added by individual instrumentors.

When instrumentors use ``enrich_metric_attributes``, it does not
overwrite base attributes that exist at the same keys.
"""

from opentelemetry.instrumentation._labeler._internal import (
    Labeler,
    clear_labeler,
    enrich_metric_attributes,
    get_labeler,
    get_labeler_attributes,
    set_labeler,
)

__all__ = [
    "Labeler",
    "get_labeler",
    "set_labeler",
    "clear_labeler",
    "get_labeler_attributes",
    "enrich_metric_attributes",
]
