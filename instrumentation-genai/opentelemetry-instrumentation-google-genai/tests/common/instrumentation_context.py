# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from opentelemetry.instrumentation.google_genai import (
    GoogleGenAiSdkInstrumentor,
)


class InstrumentationContext:
    def __init__(self, **kwargs):
        self._instrumentor = GoogleGenAiSdkInstrumentor(**kwargs)

    def install(self):
        self._instrumentor.instrument()

    def uninstall(self):
        self._instrumentor.uninstrument()
