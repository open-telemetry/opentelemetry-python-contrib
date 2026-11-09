# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Caching and compatibility wrapper for standard library ``importlib.metadata``.

This module caches ``entry_points()`` to avoid reloading entry points from disk on every call.
It also normalizes minor differences across python versions 3.10+. References to issues:

- https://github.com/open-telemetry/opentelemetry-python/pull/4735
- https://github.com/open-telemetry/opentelemetry-python/pull/5203
"""

import os
from functools import cache
from importlib.metadata import (
    Distribution,
    EntryPoint,
    EntryPoints,
    PackageNotFoundError,
    requires,
    version,
)
from importlib.metadata import distributions as _all_distributions
from typing import Any, Iterable

# opentelemetry-agent: entry points are only looked up in the vendored distributions' metadata
# (written to _vendor/_metadata by opentelemetry-vendor sync), never in the application's, whose
# OpenTelemetry plugins point at un-vendored modules. version() and requires() still see the
# application's distributions: instrumentors check the installed versions of the libraries they patch.
_VENDORED_METADATA_PATH = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "_metadata")
]


def distributions(**kwargs: Any) -> Iterable[Distribution]:
    return _all_distributions(path=_VENDORED_METADATA_PATH, **kwargs)


@cache
def _original_entry_points_cached() -> EntryPoints:
    return EntryPoints(entry_point for dist in distributions() for entry_point in dist.entry_points)


def entry_points(**params) -> EntryPoints:
    return _original_entry_points_cached().select(**params)


__all__ = [
    "Distribution",
    "EntryPoint",
    "EntryPoints",
    "PackageNotFoundError",
    "distributions",
    "entry_points",
    "requires",
    "version",
]
