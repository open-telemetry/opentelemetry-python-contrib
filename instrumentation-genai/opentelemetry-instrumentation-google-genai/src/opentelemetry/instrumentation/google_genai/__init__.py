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

from .instrumentor import GoogleGenAiSdkInstrumentor
from .version import __version__

__all__ = ['GoogleGenAiSdkInstrumentor']
