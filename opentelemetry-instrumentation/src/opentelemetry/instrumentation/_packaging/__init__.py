# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Internal, dependency-free replacements for the subset of ``packaging`` used
by OpenTelemetry instrumentation.

This package exists so that ``opentelemetry-instrumentation`` and the
instrumentations that build on it do not need ``packaging`` as a runtime
dependency. Only the behaviour actually relied on by this repository is
implemented, following PEP 440 (versions and specifiers) and PEP 508
(requirements and environment markers).
"""
