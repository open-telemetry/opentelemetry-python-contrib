# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Development APIs for HTTP client telemetry.

.. warning::
    Everything in this package is at the **Development** stability level and
    does NOT follow semantic versioning. It may have BREAKING changes in any
    release, including minor and patch releases.
"""

# Redundant ``as`` aliases mark explicit re-exports (PEP 484), which pylint does not recognize.
# pylint: disable=useless-import-alias
from opentelemetry.instrumentation.http.client._incubating._options import (
    HttpClientTelemetryDevelopmentOptions as HttpClientTelemetryDevelopmentOptions,
)
