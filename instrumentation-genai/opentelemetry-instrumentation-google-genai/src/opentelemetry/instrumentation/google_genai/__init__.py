# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

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
