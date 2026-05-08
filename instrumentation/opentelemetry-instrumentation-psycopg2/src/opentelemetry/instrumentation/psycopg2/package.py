# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


_instruments_psycopg2 = "psycopg2 >= 2.7.3.1"
_instruments_psycopg2_binary = "psycopg2-binary >= 2.7.3.1"

_instruments = ()
_instruments_any = (
    _instruments_psycopg2,
    _instruments_psycopg2_binary,
)
