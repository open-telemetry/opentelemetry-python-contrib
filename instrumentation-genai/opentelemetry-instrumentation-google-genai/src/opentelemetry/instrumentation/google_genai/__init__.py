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
Google Gen AI SDK client instrumentation supporting the `google-genai` package.

It can be enabled using ``GoogleGenAiSdkInstrumentor``.

.. _google-genai: https://pypi.org/project/google-genai/

Usage
-----

.. code:: python

    import os
    import google.genai
    from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor

    GoogleGenAiSdkInstrumentor().instrument()
    model = os.getenv('MODEL', 'gemini-2.0-flash-001')
    client = google.genai.Client()
    response = client.models.generate_content(
        model=model,
        contents='why is the sky blue?'
    )
    print(response.text)

API
---
"""

from .generate_content import GENERATE_CONTENT_EXTRA_ATTRIBUTES_CONTEXT_KEY
from .instrumentor import GoogleGenAiSdkInstrumentor
from .version import __version__

__all__ = [
    "GoogleGenAiSdkInstrumentor",
    "GENERATE_CONTENT_EXTRA_ATTRIBUTES_CONTEXT_KEY",
    "__version__",
]
