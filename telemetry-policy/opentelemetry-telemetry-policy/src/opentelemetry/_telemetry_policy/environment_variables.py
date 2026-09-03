# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE = "OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE"
"""Path to a local policy document file.

Setting it enables the file policy provider during auto-configuration.
"""

OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE_POLL_INTERVAL = (
    "OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_FILE_POLL_INTERVAL"
)
"""Seconds between policy file change checks (default 30s; 0 reads once)."""

OTEL_PYTHON_EXPERIMENTAL_OPAMP_ENDPOINT = "OTEL_PYTHON_EXPERIMENTAL_OPAMP_ENDPOINT"
"""OpAMP server URL.

Setting it enables the OpAMP policy provider during auto-configuration.
"""

OTEL_PYTHON_EXPERIMENTAL_OPAMP_IDENTIFYING_ATTRIBUTES = "OTEL_PYTHON_EXPERIMENTAL_OPAMP_IDENTIFYING_ATTRIBUTES"
"""Comma-separated resource attribute keys reported to the OpAMP server as
the agent's identifying attributes (default
``service.name,service.namespace,service.instance.id``).

Keys not present on the resource are skipped; every other resource attribute
is reported as non-identifying.
"""

OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_OPAMP_KEY = "OTEL_PYTHON_EXPERIMENTAL_TELEMETRY_POLICY_OPAMP_KEY"
"""Name of the OpAMP remote configuration entry to read the policy document
from.

An OpAMP server sends remote configuration as one or more named entries.
Set this to the entry name your server delivers policies under, for example
``vendor``. Unset, the entry with the empty name is read, which servers
commonly use when they send a single configuration.
"""
