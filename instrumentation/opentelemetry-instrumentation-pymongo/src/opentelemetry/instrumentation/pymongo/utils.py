# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

COMMAND_TO_ATTRIBUTE_MAPPING = {
    "insert": "documents",
    "delete": "deletes",
    "update": "updates",
    "find": "filter",
    "getMore": "collection",
    "aggregate": "pipeline",
}
