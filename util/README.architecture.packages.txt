OpenTelemetry GenAI Utility – Packages Snapshot (concise, plain text)
Scope covers util/ subpackages:
  opentelemetry-util-genai-dev
  opentelemetry-util-genai-emitters-splunk
  opentelemetry-util-genai-emitters-traceloop
  opentelemetry-util-genai-evals-deepeval
  opentelemetry-util-genai-evals-nltk

--------------------------------------------------------------------------------
CORE PACKAGE: opentelemetry-util-genai-dev
Purpose: Neutral GenAI data model, handler façade, builtin emitters & evaluator manager integration (refactor target -> will publish as opentelemetry-util-genai).

Key src tree (trimmed):
  src/opentelemetry/util/genai/
    __init__.py              exports public API (Handler, types, register helpers)
    version.py               package version
    config.py                runtime configuration helpers
    environment_variables.py constants & parsing for OTEL_INSTRUMENTATION_GENAI_*
    interfaces.py            core Protocols (EmitterProtocol, CompletionCallback, Sampler, Evaluator?)
    types.py                 GenAI types (LLMInvocation, AgentInvocation, ... EvaluationResult(s))
    attributes.py            semantic attribute mapping helpers / metadata extraction
    handler.py               Handler façade (start/end invocation, evaluation_results dispatch)
    callbacks.py             completion callback registration utilities
    instruments.py           metric instrument acquisition (counters, histograms, etc.)
    plugins.py               entry point discovery (emitters / evaluators)
    utils.py                 shared helpers (truncation, hashing, safe serialization)
    upload_hook.py           optional artifact / fsspec upload logic
    _fsspec_upload/          helper module(s) for remote storage (implementation detail)
    emitters/
      __init__.py            exports builtin emitter constructors
      spec.py                EmitterSpec definition (name, kind, factory, mode, position, filter)
      composite.py           CompositeEmitter (chain management, registration, fan-out)
      configuration.py       env var parsing -> chain directives
      span.py                Semantic-convention span emitter
      metrics.py             Metrics emitter (counts, latency, tokens, cost)
      content_events.py      Message content events / logs emitter
      evaluation.py          Evaluation results emitter (single vs aggregated)
      utils.py               reusable mapping & attribute extraction helpers
    evaluators/
      __init__.py            exports evaluator manager APIs
      base.py                Evaluator & Sampler protocol definitions (if not in interfaces)
      manager.py             Evaluation Manager (queue, async loop, aggregation, sampling)
      builtins.py            Placeholder/builtin evaluators (if any minimal examples)
      registry.py            Entry point discovery & instantiation of evaluators
      evaluation_emitters.py Bridge between evaluation results and handler dispatch

Principal public interfaces (summary signatures):
  class GenAIInvocation: id, parent_id, start_time_ns, end_time_ns, messages, attributes, span_context
  class LLMInvocation(GenAIInvocation): request_* / response_* semantic fields, token counts
  class EvaluationResult: metric_name, value, pass_fail?, confidence?, reasoning?, latency?, attrs
  class EvaluationResults: results: List[EvaluationResult], aggregated: bool
  class Handler:
    start_llm_invocation(...)->LLMInvocation (context manager support)
    end(invocation)
    evaluation_results(results | EvaluationResults)
    register_completion_callback(cb: CompletionCallback)
  class EmitterProtocol:
    on_start(invocation)
    on_end(invocation)
    on_evaluation_results(results_or_batch)
  class CompositeEmitter:
    register_emitter(emitter, category, *, position="last", invocation_types=None, mode="append")
  class CompletionCallback: on_completion(invocation)
  class Sampler: should_sample(invocation)->bool
  class Evaluator:
    evaluate(invocation)->List[EvaluationResult]
    default_metrics()->str

Entry point group names (expected):
  opentelemetry_util_genai_emitters (returns list[EmitterSpec])
  opentelemetry_util_genai_evaluators (returns list[Evaluator factory/spec])

Core environment variables (abbrev):
  OTEL_INSTRUMENTATION_GENAI_ENABLE=true|false
  OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES=span|events|both|none
  OTEL_INSTRUMENTATION_GENAI_EMITTERS_SPAN=...
  OTEL_INSTRUMENTATION_GENAI_EMITTERS_METRICS=...
  OTEL_INSTRUMENTATION_GENAI_EMITTERS_CONTENT_EVENTS=...
  OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION=...
  OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS=... (evaluator grammar)
  OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION=true|false

--------------------------------------------------------------------------------
EMITTERS (SPLUNK): opentelemetry-util-genai-emitters-splunk
Purpose: Vendor-specific evaluation aggregation & extended metrics/event schema for Splunk.
Key src tree:
  src/opentelemetry/util/genai/emitters/splunk.py
    Defines: SplunkEvaluationAggregator (kind="evaluation", likely replace-category)
             SplunkExtraMetricsEmitter (kind="metrics", append)
    load_emitters() -> List[EmitterSpec]
  version.py
Public focus: Provide one aggregated event containing list[EvaluationResult] + message previews; optional custom metrics (cost, agent stats).

--------------------------------------------------------------------------------
EMITTERS (TRACELOOP): opentelemetry-util-genai-emitters-traceloop
Purpose: Add Traceloop proprietary span attributes / enrich spans beyond semantic baseline.
Key src tree:
  src/opentelemetry/util/genai/emitters/traceloop.py
    TraceloopSpanEmitter (kind="span", position after SemanticConvSpan, mode append)
    load_emitters() -> List[EmitterSpec]
  version.py
Behavior: Decorates / augments baseline span emitter, adding traceloop.* attributes (model params, chain depth, etc.).

--------------------------------------------------------------------------------
EVALUATORS (DEEPEVAL): opentelemetry-util-genai-evals-deepeval
Purpose: Provide Deepeval-driven metrics (bias, toxicity, answer_relevancy, faithfulness, ...). Grammar example: Deepeval(LLMInvocation(bias,toxicity)).
Key src tree:
  src/opentelemetry/util/evaluator/deepeval.py
    DeepevalEvaluator (implements Evaluator)
    load_evaluators() / entry point factory
    default_metrics() -> str listing per invocation type
    evaluate(invocation) -> List[EvaluationResult]
  version.py

--------------------------------------------------------------------------------
EVALUATORS (NLTK): opentelemetry-util-genai-evals-nltk
Purpose: Lightweight text metrics using NLTK (readability, token_length, maybe sentiment placeholder).
Key src tree:
  src/opentelemetry/util/evaluator/nltk.py
    NLTKEvaluator (implements Evaluator)
    default_metrics() -> str
    evaluate(invocation) -> List[EvaluationResult]
  version.py

--------------------------------------------------------------------------------
ASCII LIFECYCLE (instrumented LLM call with evaluation aggregation)

  Instrumentation Code                         Emitters                     Evaluators
  ---------------------                        --------                     ----------
  with handler.start_llm_invocation() as inv:  on_start(span_emitters, ...)
       model_call()                            (spans begun, metrics prealloc)
       inv.add_output_message(...)
  # context exit
  handler.end(inv) --------------------------> on_end(span, metrics, content_events)
                |                               |      |         |
                |                               |      |         +--> message events/logs
                |                               |      +------------> latency, token metrics
                |                               +--------------------> span attributes set/end
                v
         CompletionCallbacks (Evaluator Manager) enqueue(inv)
                |
        async evaluation loop --------------> evaluators.evaluate(inv)
                | (collect List[EvaluationResult])
                v
        aggregate? (env toggle)
                |
  handler.evaluation_results(results/batch) -> on_evaluation_results(evaluation emitters)
                |
        evaluation emitters produce events/metrics (e.g. Splunk aggregated event)
                v
          OTel SDK exporters ship spans / metrics / logs

--------------------------------------------------------------------------------
Replacement / Augmentation Examples (env var shorthand)
  Add Traceloop extras: install package (auto append span emitter)
  Replace evaluation emission with Splunk aggregator:
    OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION=replace-category:SplunkEvaluationAggregator
  Custom metrics only for LLM:
    programmatic composite.register_emitter(MyLLMCostMetrics(), 'metrics', invocation_types={'LLMInvocation'})

--------------------------------------------------------------------------------
Error Handling & Perf:
  CompositeEmitter wraps each emitter call; logs + increments genai.emitter.errors(emitter,category,phase).
  Truncation + hashing utilities used before attaching large message content.
  Filter early by invocation_types to avoid serialization cost.

--------------------------------------------------------------------------------
Out-of-scope (initial): async emitters, dynamic hot-swap reconfig, advanced PII redaction, large queue backpressure.

End of concise packages architecture snapshot.
