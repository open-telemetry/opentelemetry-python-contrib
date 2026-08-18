# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


# mysql-connector-python switched to a MySQL Server aligned versioning scheme
# after 9.7.0 (the next release was 26.7.0), so no upper bound is declared here.
_instruments = ("mysql-connector-python >= 8.0",)

_semconv_status = "migration"
