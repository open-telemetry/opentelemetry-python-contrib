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

"""
Cohere client instrumentation supporting `cohere`, it can be enabled by
using ``CohereInstrumentor``.

.. note::
    This package is currently a scaffold. Chat completions instrumentation
    will be added in a follow-up PR. Installing and calling instrument() is
    safe but will not produce spans or logs until then.

.. _cohere: https://pypi.org/project/cohere/

Usage
-----

.. code:: python

    from opentelemetry.instrumentation.cohere import CohereInstrumentor

    CohereInstrumentor().instrument()

    # Chat completions patching will be wired up in a follow-up PR.

API
---
"""

from typing import Collection

from opentelemetry.instrumentation.cohere.package import _instruments
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor


class CohereInstrumentor(BaseInstrumentor):
    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs):
        """Enable Cohere instrumentation.

        TODO: Chat completions patching will be added in a follow-up PR.
        """

    def _uninstrument(self, **kwargs):
        """Disable Cohere instrumentation.

        TODO: Chat completions unpatching will be added in a follow-up PR.
        """
