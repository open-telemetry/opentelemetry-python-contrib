OpenTelemetry GenAI NLTK Evaluators
===================================

This package provides an example evaluator plug-in for the
``opentelemetry-util-genai`` project. It exposes an entry point that
registers an ``nltk`` sentiment evaluator which mirrors the reference
implementation that previously lived in the dev bundle.

Installation
------------

.. code-block:: bash

   pip install opentelemetry-util-genai-evals-nltk

The package depends on ``nltk`` and will ensure the library is installed.
If you have not previously downloaded the VADER lexicon run:

.. code-block:: python

   import nltk
   nltk.download("vader_lexicon")

Usage
-----

After installation the evaluator becomes available under the name
``nltk_sentiment`` and can be activated via the environment variable
``OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS``:

.. code-block:: bash

   export OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS="length,nltk_sentiment"

The evaluator inspects LLM invocation outputs and emits an
``EvaluationResult`` containing the VADER compound score plus a labelled
sentiment bucket (``positive``, ``neutral`` or ``negative``).

This package follows the same entry-point pattern as the other
evaluator plug-ins (see ``opentelemetry-util-genai-evals-deepeval`` for a
more advanced example).
