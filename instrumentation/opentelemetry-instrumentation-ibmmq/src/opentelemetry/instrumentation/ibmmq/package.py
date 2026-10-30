# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Collection

_instruments_ibmmq = "ibmmq >= 2.0, < 3.0"
_instruments_pymqi = "pymqi >= 1.12, < 2.0"

_instruments: Collection[str] = ()
_instruments_any: Collection[str] = (_instruments_ibmmq, _instruments_pymqi)
_semconv_status = "development"
