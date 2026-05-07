# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


_instruments_kafka_python = "kafka-python >= 2.0, < 3.0"
_instruments_kafka_python_ng = "kafka-python-ng >= 2.0, < 3.0"

_instruments = ()
_instruments_any = (_instruments_kafka_python, _instruments_kafka_python_ng)
