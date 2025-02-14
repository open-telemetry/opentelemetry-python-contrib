# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys

sys.path.append("../../src")

# This import has to happen after 'sys.path.append' above, so that it is possible
# to use this name relative to "../../src" (at least when this module is imported
# from a test script that has been invoked directly).
from opentelemetry.instrumentation.google_genai import (  # pylint: disable=wrong-import-position
    GoogleGenAiSdkInstrumentor,
)


class InstrumentationContext:

    def __init__(self):
        self._instrumentor = GoogleGenAiSdkInstrumentor()

    def install(self):
        self._instrumentor.instrument()

    def uninstall(self):
        self._instrumentor.uninstrument()
