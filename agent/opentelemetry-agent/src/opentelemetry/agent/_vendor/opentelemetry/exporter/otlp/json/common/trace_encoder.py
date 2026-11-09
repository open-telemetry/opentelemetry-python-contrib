# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from opentelemetry.agent._vendor.opentelemetry.exporter.otlp.json.common._internal.trace_encoder import (
    encode_spans,
)

__all__ = ["encode_spans"]
