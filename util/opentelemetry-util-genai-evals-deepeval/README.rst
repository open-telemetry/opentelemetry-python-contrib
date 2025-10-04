OpenTelemetry GenAI Utilities Evals for Deepeval (opentelemetry-util-genai-evals-deepeval)
==========================================================================================

This package plugs the `deepeval <https://github.com/confident-ai/deepeval>`_ metrics
suite into the OpenTelemetry GenAI evaluation pipeline. When it is installed a
``Deepeval`` evaluator is registered automatically and, unless explicitly disabled,
is executed for every LLM/agent invocation alongside the builtin metrics.

Requirements
------------

* ``deepeval`` and its transitive dependencies (installed automatically).
* An LLM provider supported by Deepeval. By default the evaluator uses OpenAI's
  ``gpt-4o-mini`` model because it offers the best balance of latency and cost
  for judge workloads right now, so make sure ``OPENAI_API_KEY`` is available.
  To override the model, set ``DEEPEVAL_EVALUATION_MODEL`` (or ``DEEPEVAL_MODEL`` /
  ``OPENAI_MODEL``) to a different deployment along with the corresponding
  provider credentials.
* (Optional) ``DEEPEVAL_API_KEY`` if your Deepeval account requires it.

Configuration
-------------

Use ``OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS`` to select the metrics that
should run. Leaving the variable unset enables every registered evaluator with its
default metric set. Examples:

* ``OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS=Deepeval`` – run the default
  Deepeval bundle (Bias, Toxicity, Answer Relevancy, Faithfulness).
* ``OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS=Deepeval(LLMInvocation(bias(threshold=0.75)))`` –
  override the Bias threshold for LLM invocations and skip the remaining metrics.
* ``OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS=none`` – disable the evaluator entirely.

Results are emitted through the standard GenAI evaluation emitters (events,
metrics, spans). Each metric includes helper attributes such as
``deepeval.success``, ``deepeval.threshold`` and any evaluation model metadata
returned by Deepeval. Metrics that cannot run because required inputs are missing
(for example Faithfulness without a ``retrieval_context``) are marked as
``label="skipped"`` and carry a ``deepeval.error`` attribute so you can wire the
necessary data or disable that metric explicitly.
