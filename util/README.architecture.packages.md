# OpenTelemetry GenAI Utility – Packages Snapshot (Concise)

Scope (util/ subpackages):
`opentelemetry-util-genai-dev`, `opentelemetry-util-genai-emitters-splunk`, `opentelemetry-util-genai-emitters-traceloop`, `opentelemetry-util-genai-evals-deepeval`, `opentelemetry-util-genai-evals-nltk`

---
## Core Package: opentelemetry-util-genai-dev
Purpose: Neutral GenAI data model + handler façade + builtin emitters + evaluator manager integration (refactor target -> final `opentelemetry-util-genai`).

Directory (trimmed):
```text
src/opentelemetry/util/genai/
  __init__.py              # public API exports
  version.py               # version constant
  config.py                # runtime config helpers
  environment_variables.py # OTEL_INSTRUMENTATION_GENAI_* parsing
  interfaces.py            # Protocols (EmitterProtocol, CompletionCallback, Sampler, Evaluator)
  types.py                 # GenAI types (LLMInvocation, AgentInvocation, ... EvaluationResult(s))
  attributes.py            # semantic attribute metadata extraction
  handler.py               # Handler façade (start/end, evaluation dispatch)
  callbacks.py             # completion callback registration
  instruments.py           # metric instruments (counters, histograms, gauges)
  plugins.py               # entry point discovery (emitters, evaluators)
  utils.py                 # truncation, hashing, safe serialization
  upload_hook.py           # optional artifact/fsspec upload
  _fsspec_upload/          # helper modules (impl detail)
  emitters/
    __init__.py
    spec.py                # EmitterSpec (name, kind, factory, mode, position, filter)
    composite.py           # CompositeEmitter (chains + fan-out)
    configuration.py       # env var chain directives parsing
    span.py                # semantic-convention span emitter
    metrics.py             # metrics emitter
    content_events.py      # message content events/logs
    evaluation.py          # evaluation result(s) emitter
    utils.py               # shared mapping helpers
  evaluators/
    __init__.py
    base.py                # Evaluator & Sampler protocols (if not in interfaces)
    manager.py             # Evaluation Manager (queue, async loop, aggregation)
    builtins.py            # placeholder / builtin evaluators
    registry.py            # evaluator entry point loading
    evaluation_emitters.py # bridge to handler.evaluation_results
```

Interfaces (summary):
```python
class GenAIInvocation: ...
class LLMInvocation(GenAIInvocation): ...  # request_*/response_* semantic fields, token counts
class EvaluationResult: metric_name, value, pass_fail?, confidence?, reasoning?, latency?, attrs
class EvaluationResults: results: list[EvaluationResult]; aggregated: bool

class Handler:
    def start_llm_invocation(...)->LLMInvocation: ...  # context manager
    def end(invocation): ...
    def evaluation_results(results | EvaluationResults): ...
    def register_completion_callback(cb: CompletionCallback): ...

class EmitterProtocol(Protocol):
    def on_start(invocation): ...
    def on_end(invocation): ...
    def on_evaluation_results(results_or_batch): ...

class CompositeEmitter:
    def register_emitter(emitter, category, *, position="last", invocation_types=None, mode="append"): ...

class CompletionCallback: def on_completion(invocation): ...
class Sampler: def should_sample(invocation)->bool: ...
class Evaluator:
    def evaluate(invocation)->list[EvaluationResult]: ...
    def default_metrics()->str: ...
```

Entry points:
```text
opentelemetry_util_genai_emitters   # returns list[EmitterSpec]
opentelemetry_util_genai_evaluators # returns list[Evaluator factory/spec]
```

Environment variables (subset):
```text
OTEL_INSTRUMENTATION_GENAI_ENABLE=true|false
OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGES=span|events|both|none
OTEL_INSTRUMENTATION_GENAI_EMITTERS_SPAN=...
OTEL_INSTRUMENTATION_GENAI_EMITTERS_METRICS=...
OTEL_INSTRUMENTATION_GENAI_EMITTERS_CONTENT_EVENTS=...
OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION=...
OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS=...
OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION=true|false
```

---
## Emitters Package: opentelemetry-util-genai-emitters-splunk
Purpose: Splunk-specific evaluation aggregation + extra metrics/events.
```text
src/opentelemetry/util/genai/emitters/splunk.py
  SplunkEvaluationAggregator  # kind="evaluation" (often replace-category)
  SplunkExtraMetricsEmitter   # kind="metrics" (append)
  load_emitters() -> list[EmitterSpec]
version.py
```

---
## Emitters Package: opentelemetry-util-genai-emitters-traceloop
Purpose: Traceloop proprietary span enrichment.
```text
src/opentelemetry/util/genai/emitters/traceloop.py
  TraceloopSpanEmitter        # kind="span" position after SemanticConvSpan
  load_emitters() -> list[EmitterSpec]
version.py
```

---
## Evaluators Package: opentelemetry-util-genai-evals-deepeval
Purpose: Deepeval metrics (bias, toxicity, answer_relevancy, faithfulness, ...).
Grammar example: `Deepeval(LLMInvocation(bias,toxicity))`.
```text
src/opentelemetry/util/evaluator/deepeval.py
  DeepevalEvaluator           # implements Evaluator
  load_evaluators()           # entry point factory
  default_metrics()           # per invocation type string
  evaluate(invocation)        # -> list[EvaluationResult]
version.py
```

---
## Evaluators Package: opentelemetry-util-genai-evals-nltk
Purpose: Lightweight NLTK-based text metrics (readability, token length, etc.).
```text
src/opentelemetry/util/evaluator/nltk.py
  NLTKEvaluator               # implements Evaluator
  default_metrics()
  evaluate(invocation)
version.py
```

---
## ASCII Lifecycle (LLM invocation with evaluations)
```text
Instrumentation         Emitters (Composite)                     Evaluators
--------------          ---------------------                    ----------
with handler.start_llm_invocation() as inv:  on_start(span, metrics, ...)
    model_call()                             (spans begun, metrics prealloc)
    inv.add_output_message(...)
handler.end(inv) --------> on_end(span, metrics, content_events)
        |                        |     |         |
        |                        |     |         +--> message events/logs
        |                        |     +------------> latency / tokens metrics
        |                        +------------------> span attrs + end
        v
  CompletionCallbacks (Evaluator Manager) enqueue(inv)
        |
  async loop ------------> evaluators.evaluate(inv) -> [EvaluationResult]
        | aggregate? (env toggle)
        v
handler.evaluation_results(batch|single) -> on_evaluation_results(evaluation emitters)
        |
  evaluation events/metrics (e.g. Splunk aggregated)
        v
OTel SDK exporters send spans / metrics / logs
```

---
## Replacement / Augmentation Examples
```text
Add Traceloop extras:
  (install package) -> auto append TraceloopSpanEmitter

Replace evaluation emission with Splunk aggregator:
  OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION=replace-category:SplunkEvaluationAggregator

Custom metrics only for LLM:
  composite.register_emitter(MyLLMCostMetrics(), 'metrics', invocation_types={'LLMInvocation'})
```

---
## Error & Performance Notes
```text
Emitter errors caught; increment genai.emitter.errors(emitter,category,phase).
Truncation + hashing before large message content emission.
Invocation-type filtering before heavy serialization.
Heavy enrichments -> evaluator layer (keep emitters lightweight).
```

---
## Out of Scope (Initial)
```text
Async emitters, dynamic hot-swap reconfig, advanced PII redaction, large queue backpressure.
```

---
End of concise packages architecture snapshot.
