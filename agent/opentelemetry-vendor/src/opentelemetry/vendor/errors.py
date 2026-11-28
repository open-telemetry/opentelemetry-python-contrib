# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations


class VendorError(Exception):
    """Base class for errors reported to the user by ``opentelemetry-vendor``."""
