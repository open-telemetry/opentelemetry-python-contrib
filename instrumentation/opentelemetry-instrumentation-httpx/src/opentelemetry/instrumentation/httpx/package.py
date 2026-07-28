# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

_instruments_httpx = ("httpx >= 0.18.0",)
_instruments_httpx2 = ("httpx2 >= 2.0.0",)

_instruments = ()
_instruments_any = (*_instruments_httpx, *_instruments_httpx2)

_supports_metrics = True

_semconv_status = "migration"
