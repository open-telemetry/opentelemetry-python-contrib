# GenAI Emitters Refactor Demo Scenarios

This document extends the base demo guide and walks through distinct scenarios mapped to the reference architecture:

Scenarios:
1. Standard semantic convention telemetry (baseline spans + metrics + optional content)  
2. Switch content from span attributes to events (content events flavor)  
3. Enable builtin evaluators via environment variable  
4. Install and auto-register Deepeval evaluators  
5. Install NLTK sentiment evaluator plug-in  
6. Switch to Traceloop telemetry flavor (after installing package)  
7. Replace evaluation emission with Splunk evaluation aggregator (after installing Splunk emitters package)  

> All commands assume an active virtual environment inside the repo root and a running OpenTelemetry Collector at `localhost:4317` (gRPC). Replace secret placeholders. Do not commit secrets.

---
## Common Setup (Once)
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# Core editable installs
pip install -e instrumentation-genai/opentelemetry-instrumentation-langchain-dev
pip install -e util/opentelemetry-util-genai-dev

# OTLP exporter & core APIs (if not already present via deps)
pip install -e opentelemetry-api -e opentelemetry-sdk -e opentelemetry-semantic-conventions
pip install -e exporter/opentelemetry-exporter-otlp-proto-grpc

# LangChain & OpenAI interface
pip install langchain langchain_openai
```

Export shared environment (excluding scenario-specific toggles):
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
export OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
export OTEL_LOGS_EXPORTER="otlp"
export OTEL_SERVICE_NAME="demo-app-util-genai-dev"
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=o11y-for-ai-dev-sergey"
export OTEL_SEMCONV_STABILITY_OPT_IN="gen_ai_latest_experimental"
# Credentials (placeholders)
export CISCO_CLIENT_ID="<cisco-client-id>"
export CISCO_CLIENT_SECRET="<cisco-client-secret>"
export CISCO_APP_KEY="<cisco-app-key>"
# Optional
# export OPENAI_API_KEY="<openai-key>"
```

Run command used in every scenario unless noted:
```bash
python instrumentation-genai/opentelemetry-instrumentation-langchain-dev/examples/manual/main.py
```

Collector Expectations (generic):
- Traces pipeline receives spans named for LLM invocations (and later evaluation spans if enabled).
- Metrics pipeline receives invocation duration + evaluation score histogram (may be empty if no evaluations).
- Logs/Events pipeline receives message content events and evaluation events (when configured), plus any vendor-specific events after package installation.

---
## Scenario 1: Standard Semantic Convention Telemetry
Goal: Baseline spans + metrics; keep messages attached to spans (simplest path).

Env:
```bash
export OTEL_INSTRUMENTATION_GENAI_EMITTERS="span_metric"  # spans + metrics only
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="true"  # attach content to spans
unset OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE 2>/dev/null || true
```
Run the demo.

Expect in Collector:
- Spans containing message content attributes (input/output).  
- No separate content events (logs count near zero for message events).  
- Metrics: latency + any token metrics exposed.  
- Evaluation histogram present (no points unless evaluators later enabled).

---
## Scenario 2: Switch Content from Span Attributes to Events
Goal: Make spans lean; move messages to separate events/log records.

Env:
```bash
export OTEL_INSTRUMENTATION_GENAI_EMITTERS="span_metric_event"  # enable content events category
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE="EVENT_ONLY"  # or SPAN_AND_EVENT
```
Run the demo.

Expect:
- Spans with minimal or no full message bodies (may still have counts/roles).  
- Logs/Events: one event per message (`role`, ordering index).  
- Metrics unchanged.

Verification Tips:
- Compare span attribute size vs Scenario 1.  
- Count events per invocation = (#input + #output + #system messages).

---
## Scenario 3: Enable Builtin Evaluators (Implemented)
Builtin evaluators shipped today: `length` (name lowercase). They apply only to `LLMInvocation` objects. Additional evaluators such as sentiment analysis are available via optional packages (for example `opentelemetry-util-genai-evals-nltk`).

Env additions on top of Scenario 2 (content events flavor is a good baseline for evaluation clarity):
```bash
export OTEL_INSTRUMENTATION_GENAI_EMITTERS="span_metric_event"
export OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE="EVENT_ONLY"
# Enable evaluators (example syntax—adjust to actual implemented variable names if they differ)
export OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS="length"
export OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION="true"     # aggregate all results per invocation
```
Run the demo.

- Each evaluation result produces its own `gen_ai.evaluation` event; the builtin length evaluator always yields a numeric score.
- If optional evaluator packages (e.g., `opentelemetry-util-genai-evals-nltk`) are installed, include them in `OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS` alongside `length` (e.g., `length,nltk_sentiment`). These packages manage their own dependencies such as NLTK/VADER.
- Histogram `gen_ai.evaluation.score` receives one point per numeric result emitted by the active evaluators (length is always numeric; additional evaluators may emit numeric or error-only results depending on their dependencies).
- Invocation span attribute `gen_ai.evaluation.executed=true` set when at least one evaluator ran.

If not visible:
- Confirm evaluator variable names match current branch implementation.
- Check logs for evaluator load warnings.

---
## Scenario 4: Install and Auto-Register Deepeval (Forward-Looking)
Goal: Demonstrate 3rd-party evaluator entry point registration (e.g., toxicity, bias). This assumes a Deepeval adapter package exposing entry points under `opentelemetry_util_genai_evaluators`. If such an adapter is not yet published this scenario will currently no-op (you will only see builtin evaluators).

Install (plus any deepeval model-specific extras you require):
```bash
pip install deepeval
```

The Deepeval plug-in included in this repo automatically opts Deepeval out of
its internal telemetry so the demo traces remain focused on application spans.
Set ``DEEPEVAL_TELEMETRY_OPT_OUT=0`` before launch if you need to re-enable the
vendor telemetry.

Env (build on Scenario 3):
```bash
# Syntax: evaluatorName(TypeName(metricA,metricB))[,nextEvaluator]
# Deepeval metrics usually target LLMInvocation, so scope explicitly.
export OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS="deepeval(LLMInvocation(toxicity,bias)),length"
export OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION="true"
```
Run the demo.

Expect (once adapter implemented):
- Additional per-result events for metrics such as `toxicity`, `bias`, and the builtin `length`.
- Histogram `gen_ai.evaluation.score` includes new metric points (assuming numeric scores).
- Errors (e.g., model not loaded) appear as evaluation events with the `error` field populated instead of a numeric score.

Troubleshooting:
- If only `length` appears: Deepeval adapter entry point not present; verify `pip show` for adapter package.
- If deepeval installed but metrics missing: set `OTEL_LOG_LEVEL=debug` and look for "Evaluator 'deepeval' is not registered" warning.

---
## Scenario 5: Install NLTK Sentiment Evaluator Plug-in
Goal: Add the optional NLTK/VADER sentiment evaluator via the new plug-in package.

Install (editable from this repo or published wheel):
```bash
pip install -e util/opentelemetry-util-genai-evals-nltk  # or pip install opentelemetry-util-genai-evals-nltk
```

Optional: download the VADER lexicon if not already cached (one-time):
```python
python -c "import nltk; nltk.download('vader_lexicon')"
```

Env (build on Scenario 3 configuration):
```bash
export OTEL_INSTRUMENTATION_GENAI_EVALS_EVALUATORS="length,nltk_sentiment"
export OTEL_INSTRUMENTATION_GENAI_EVALS_RESULTS_AGGREGATION="true"
```

Run the demo.

Expect:
- Additional evaluation results with metric name `sentiment` containing the VADER-derived score and label (`positive`, `neutral`, `negative`).
- Histogram `gen_ai.evaluation.score` receives an extra point per invocation for the sentiment result when the dependency is available.
- If NLTK or the VADER lexicon is missing the evaluator emits an `EvaluationResult` with the `error` field populated (no score) so that failures remain observable.

Troubleshooting:
- Ensure the plug-in package is installed in the active environment (`pip show opentelemetry-util-genai-evals-nltk`).
- If you see missing dependency errors, verify that both `nltk` and the VADER data set are installed.

---
## Scenario 6: Switch to Traceloop Telemetry Flavor
Goal: Demonstrate vendor-style span attribute extension by appending Traceloop emitter.

Install the Traceloop plug-in from this repo (or the published wheel when available):
```bash
pip install -e util/opentelemetry-util-genai-emitters-traceloop
```
Env (start from Scenario 2 or 3 config):
```bash
export OTEL_INSTRUMENTATION_GENAI_EMITTERS="span_metric_event,traceloop_compat"
```
Run the demo.

Expect:
- Additional Traceloop-compatible span per invocation OR enriched attributes added by appended emitter.  
- Distinguish via attribute namespace (e.g., `traceloop.*`).  
- Core semantic spans still present for portability.

If not visible:
- Verify package exposes entry point group `opentelemetry_util_genai_emitters` and name matches expected spec list.

---
## Scenario 7: Splunk Evaluation Aggregator (Replace Evaluation Chain)
Goal: Replace standard evaluation emitters with Splunk aggregator + append extra metrics.

Install:
```bash
pip install opentelemetry-util-genai-emitters-splunk
```
Env (build on Scenario 4 or Scenario 5 so that evaluations are enabled):
```bash
export OTEL_INSTRUMENTATION_GENAI_EMITTERS_EVALUATION="replace-category:SplunkEvaluationAggregator"
export OTEL_INSTRUMENTATION_GENAI_EMITTERS_METRICS="append:SplunkExtraMetricsEmitter"  # example name
# Maintain base flavor for spans & content events
export OTEL_INSTRUMENTATION_GENAI_EMITTERS="span_metric_event"
```
Run the demo.

Expect:
- Evaluation events now consolidated into a single Splunk-formatted event per invocation (message previews, aggregated scores).  
- Default evaluation events absent (replaced).  
- Metrics: additional vendor metrics (cost, usage, or custom) alongside baseline histograms.  
- Evaluation spans behave per span mode (if Splunk aggregator emits them or suppresses duplicates).

Troubleshooting:
- If default evaluation events still appear: ensure the exact directive syntax `replace-category:` is supported by current refactor implementation (some early code may only parse `replace-category` in env overrides; double-check builder logic).
- If vendor metrics absent: confirm emitter spec name matches env directive.

---
## Comparative Signal Checklist
| Scenario | Span Content | Content Events | Evaluation Events | Evaluation Spans | Vendor Spans | Extra Metrics |
|----------|--------------|----------------|-------------------|------------------|--------------|---------------|
| 1 Baseline | Full messages | No | No | No | No | No |
| 2 Events   | Minimal | Yes | No | No | No | No |
| 3 Builtin Eval | Minimal | Yes | One event per builtin result | No | No | No |
| 4 Deepeval | Minimal | Yes | One event per Deepeval result | No | No | No |
| 5 NLTK Plug-in | Minimal | Yes | One event per builtin + NLTK result | No | No | No |
| 6 Traceloop | Minimal | Yes | Matches prior scenario | No | Yes | No |
| 7 Splunk | Minimal | Yes | Single vendor aggregated event | No | Optional (unchanged) | Yes (vendor) |

---
## Verification Scripts (Optional Quick Checks)
These can be adapted to query your backend (pseudo examples):
```bash
# Count spans by service
# (If using collector with logging exporter add a simple grep)
# grep '"name":' collector-trace-log.json | grep demo-app-util-genai-dev | wc -l

# Check evaluation events (logs)
# grep 'gen_ai.evaluation' collector-logs.json | wc -l
```

---
## Notes on Implementation Gaps
- Invocation type filtering (EmitterSpec.invocation_types) may not yet be enforced; scenarios assume future alignment.
- Traceloop & Splunk external packages require their own entry points; if not published, scenario serves as forward-looking example.
- Deepeval scenario is forward-looking until an adapter provides the evaluator entry point. The included plug-in disables Deepeval's internal telemetry by default; set ``DEEPEVAL_TELEMETRY_OPT_OUT=0`` to re-enable vendor spans.
- Adjust environment variable names if subsequent refactor tasks rename or consolidate evaluation toggles.

### Current Built-in Metric Instruments
Emitted today when corresponding emitters are enabled:
- gen_ai.client.operation.duration (Histogram)
- gen_ai.client.token.usage (Histogram)
- gen_ai.workflow.duration (Histogram)
- gen_ai.agent.duration (Histogram)
- gen_ai.task.duration (Histogram)
- gen_ai.evaluation.score (Histogram of numeric evaluation scores)

Token usage attributes also appear on spans (gen_ai.usage.input_tokens / output_tokens) and are bucketed into gen_ai.client.token.usage when MetricsEmitter is active.

---
## Cleanup
```bash
deactivate
rm -rf .venv
```
Remove token cache (`/tmp/.token.json`) and unset sensitive variables.

---
**End of Scenario Guide**
