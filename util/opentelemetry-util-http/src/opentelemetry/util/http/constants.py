# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Constants for OpenTelemetry HTTP utilities.

This module contains configuration constants and pattern definitions used
by HTTP instrumentation utilities for various features like synthetic user
agent detection.
"""

# Test patterns to detect in user agent strings (case-insensitive)
# These patterns indicate synthetic test traffic
TEST_PATTERNS = [
    "alwayson",
]

# Bot patterns to detect in user agent strings (case-insensitive)
# These patterns indicate automated bot traffic
BOT_PATTERNS = [
    "googlebot",
    "bingbot",
]
