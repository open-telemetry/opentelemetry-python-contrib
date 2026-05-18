# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


_instruments_cassandra_driver = "cassandra-driver ~= 3.25"
_instruments_scylla_driver = "scylla-driver ~= 3.25"

_instruments = ()
_instruments_any = (_instruments_cassandra_driver, _instruments_scylla_driver)
