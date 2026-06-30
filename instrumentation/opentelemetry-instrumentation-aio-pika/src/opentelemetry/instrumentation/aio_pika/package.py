# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from typing import Collection

_instruments: Collection[str] = ("aio_pika >= 7.2.0, < 10.0.0",)

_instrumentation_name: Final[str] = "opentelemetry.instrumentation.aio_pika"
