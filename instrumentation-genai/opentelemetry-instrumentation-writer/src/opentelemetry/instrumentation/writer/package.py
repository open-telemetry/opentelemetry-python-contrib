# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

# The chat/completions resources and their ``Stream``-based streaming, ``Omit``
# sentinel, and response/chunk shapes used by this instrumentation have been
# stable across the writerai 3.x-4.x line. writerai has no 2.0.x release on PyPI
# (versions jump from 1.2.4 to 3.0.0), so ``>= 3.0.0`` is the sane lower bound.
_instruments = ("writerai >= 3.0.0",)

_supports_metrics = True
