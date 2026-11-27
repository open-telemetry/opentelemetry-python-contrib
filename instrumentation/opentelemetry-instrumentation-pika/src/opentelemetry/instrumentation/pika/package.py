# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Collection
from typing import Final

_instruments: Collection[str] = ("pika >= 0.12.0",)

_instrumentation_name: Final[str] = "opentelemetry.instrumentation.pika"
