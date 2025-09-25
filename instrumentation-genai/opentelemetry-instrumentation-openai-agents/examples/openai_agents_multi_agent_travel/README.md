# Multi-Agent Travel Planning (OpenAI Agents + OpenTelemetry)

This folder now contains **two** illustrative examples of instrumented multi-agent travel planning using the OpenAI Agents API and OpenTelemetry:

1. `multi_travel_planner.py` – A concise, faster single-agent orchestration that chains a few simple function tools (geocode / weather / cuisine). Good for a quick look at instrumentation wiring and a minimal trace.
2. `enhanced.py` – A richer, production-style multi‑agent workflow that mirrors a LangGraph style handoff pipeline (Coordinator → Flight → Hotel → Activity → Budget → Plan Synthesizer). It demonstrates structured outputs, tool usage, deterministic handoffs, OpenTelemetry spans, and interactive fallbacks when the model asks clarifying questions.


## Why the Enhanced Version?

`enhanced.py` showcases patterns often needed in real systems:

* Multiple cooperating specialist agents with explicit handoff definitions.
* Structured extraction via Pydantic (`TripDetails`, `FlightRecommendation`, etc.).
* Automatic tracing of each agent invocation and tool execution via `opentelemetry-instrumentation-openai-agents`.
* A resilient trip detail parsing layer (JSON parsing + heuristic extraction) and an **interactive fallback prompt flow** (so a model asking for missing info doesn’t crash the pipeline).
* Budget analysis + synthesis phase to create a cohesive final plan.
* Per‑agent model instances (can vary temperature / deployment) while retaining a single end‑to‑end workflow trace.


## Features Comparison

| Capability | multi_travel_planner.py | enhanced.py |
|------------|-------------------------|-------------|
| Simple single pass | ✅ | ➖ (multi-step) |
| Deterministic multi-agent chain | ❌ | ✅ |
| Structured Pydantic outputs | Minimal | Extensive |
| Interactive fallback for missing details | ❌ | ✅ |
| Budget computation | ❌ | ✅ |
| Day-by-day itinerary synthesis | ❌ | ✅ |
| Rich span hierarchy | Basic | Deep (per agent + tools) |


## Quick Start (Both Scripts)

```bash
cp .env.example .env   # fill in Azure OpenAI endpoint, key, deployment
pip install -r requirements.txt
```

Ensure one of these is configured:

* Azure: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`
* or Public OpenAI: `OPENAI_API_KEY` and (optionally) `OPENAI_MODEL`

Optional OpenTelemetry exporter vars (see `.env.example`):

* `OTEL_EXPORTER_OTLP_ENDPOINT`
* `OTEL_EXPORTER_OTLP_HEADERS`
* Set instrumentation content capture toggles such as `OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT=true` for message/tool IO.

---

## Running the Simple Planner

```bash
python multi_travel_planner.py --city "Paris" --date 2025-09-10
```

---

## Running the Enhanced Multi-Agent Planner

Interactive mode (default):

```bash
python enhanced.py
```

You will be shown sample requests. Press Enter to accept a sample or paste your own natural language trip description. If the coordinator agent requests clarification (e.g., missing origin or dates), the script will prompt you to enter the missing fields.

Non-interactive strict mode (fail instead of prompting):

```bash
export INTERACTIVE_TRIP_DETAILS=0
python enhanced.py
```

### Sample Natural Language Requests

Copy these into the prompt (or just press Enter to use one automatically):

* Business: “I need to plan a business trip to London for 3 days from Seattle, hotel near the financial district, efficient flights, budget around $3000.”
* Family: “Plan a family vacation to Paris for 2 adults and 2 children for 10 days next month. Museums, parks, family-friendly activities, about $8000 total.”
* Romantic: “Romantic anniversary trip to Tokyo for a week, luxury hotel, fine dining, up to $6000.”

---

## Interactive Fallback Details (`enhanced.py`)

If the coordinator LLM answer is a *clarifying question* rather than a structured JSON-like response, the script attempts:

1. JSON parse (if the model returned JSON).
2. Heuristic extraction (regex for origin/destination/dates/duration/budget/trip type).
3. If still incomplete and `INTERACTIVE_TRIP_DETAILS != 0`, prompt you for the remaining fields.

Disable this by setting `INTERACTIVE_TRIP_DETAILS=0` to force a hard error (useful in CI or automated evaluations).

---

## Observability

Both scripts rely on `OpenAIAgentsInstrumentor` which creates spans such as:

* Root span: workflow invocation (`gen_ai.operation.name=invoke_agent`).
* Child spans: each agent call + each function tool execution (`execute_tool`).
* Attributes: model metadata, tool names, (optionally) message content and structured outputs.

To view data:

* Console exporter (default) prints spans to stdout.
* Set OTLP exporter variables to ship to Azure Monitor / another backend.

---

## Extending `enhanced.py`

Ideas:

* Add real API-backed tools (live flights, hotels, weather) – instrumentation is unchanged.
* Introduce retry + guardrails (ask the model to reformat invalid structured output before falling back to manual input).
* Cache intermediate tool results for iterative refinement.
* Emit custom span events for milestones (e.g., “flights_selected”, “budget_locked”).

---

## Troubleshooting

| Issue | Possible Cause | Fix |
|-------|----------------|-----|
| Coordinator asks for origin/dates repeatedly | Insufficient initial prompt detail | Provide explicit origin, destination, ISO dates |
| ValueError about TripDetails in strict mode | Missing required fields & fallback disabled | Remove `INTERACTIVE_TRIP_DETAILS=0` or add details |
| No spans exported externally | OTLP env vars not set | Provide OTLP endpoint + headers or keep console export |
| Model name not found | Wrong deployment/model env | Check `AZURE_OPENAI_DEPLOYMENT` or `OPENAI_MODEL` |

---

## Next Steps

* Add more specialized tools (exchange rates, safety alerts, local transit).
* Integrate a vector store for preference memory across sessions.
* Emit custom OpenTelemetry events for major planning milestones.
* Package this example as a reusable reference for multi-agent orchestration + observability.

---
Happy exploring! Feel free to adapt `enhanced.py` to your own domain—any new agent or tool automatically participates in tracing once it flows through the `Runner` and instrumentation hooks.

---

## Evaluation & Metrics (Trace Post-Processing)

The script `evaluate_trace_agents.py` lets you retroactively score agent invocations captured in Application Insights (or any backend you forward spans to) and emit structured GenAI evaluation events. It targets spans where `gen_ai.operation.name=invoke_agent`.

### Capabilities

* Trace retrieval (REST or LogsQueryClient) for a given trace ID.
* Automatic identification of agent invocation spans.
* Extraction of input/output messages, tool call child spans, and tool definitions.
* Emission of two event types (aligned with draft semantic conventions):
  * `gen_ai.client.inference.operation.details`
  * `gen_ai.evaluation.result`
* Evaluation metrics (model-based when `azure-ai-evaluation` is installed, otherwise heuristics):
  * IntentResolution
  * ToolCallAccuracy (only if tool calls/definitions present)
  * TaskAdherence
* Verification pass: optional re-query to confirm evaluation events ingestion.
* JSON artifact summarizing scores, averages, and pass rates.

### Usage

```bash
python evaluate_trace_agents.py --trace-id <operation_Id>
# limit to specific invoke_agent span(s)
python evaluate_trace_agents.py --trace-id <operation_Id> --span-id <span_id>

# Customize threshold & disable certain emissions
python evaluate_trace_agents.py --trace-id <operation_Id> \
  --threshold 3.5 --no-operation-event
```

Output: `eval_<trace-id>.json` (unless `--output` supplied) and emitted events.

### Key Environment Variables

Query (choose one path):

* REST: `APP_INSIGHTS_APP_ID`, `APPLICATION_INSIGHTS_API_KEY`
* Logs API (AAD): `APPLICATION_INSIGHTS_RESOURCE_ID`, plus Azure AD creds (tenant/client/secret or managed identity)

Export / Emission:

* `APPLICATIONINSIGHTS_CONNECTION_STRING` (or legacy `APPLICATION_INSIGHTS_CONNECTION_STRING`)
* `OTEL_EXPORTER_OTLP_ENDPOINT` (optional additional export)

Evaluation Toggles / Config:

* `EVAL_EMIT_OPERATION_DETAILS=1`
* `EVAL_EMIT_EVALUATIONS=1`
* `EVAL_VERIFICATION=1`
* `EVAL_THRESHOLD=3.0`
* `EVAL_LOOKBACK_MINS=30`
* `EVAL_MODEL_DEPLOYMENT` / `EVAL_MODEL` / `AZURE_OPENAI_DEPLOYMENT`
* `EVAL_MAX_MESSAGE_CHARS=20000`

Azure OpenAI (for model-based evaluators):

* `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`

### Events Emitted

`gen_ai.client.inference.operation.details` (one per evaluated span, opt-in)

* Includes request/response model metadata, input/output messages (truncated), system instructions, tool definitions, usage counts.

`gen_ai.evaluation.result` (one per metric)

* Attributes: `gen_ai.evaluation.name`, `.score.value`, `.score.label`, `.evaluation.explanation`, optional `gen_ai.response.id`, token usage, and `error.type` if applicable.

### Heuristic vs Model-Based

If `azure-ai-evaluation` is absent or Azure OpenAI credentials are missing, the script applies heuristics:

* IntentResolution (heuristic): overlap of significant query tokens in the response.
* ToolCallAccuracy (heuristic): fraction of tool names mentioned in the final answer.
* TaskAdherence (heuristic): length/coverage based score.

### Dependency Additions

Add (if not already present) to `requirements.txt` for evaluation:

```text
azure-monitor-query
azure-identity
requests
azure-ai-evaluation  # optional; enables model-based metrics
```

(`opentelemetry-*`, `azure-monitor-opentelemetry-exporter`, and `python-dotenv` are already used by the main examples.)

### Common Issues

| Issue | Cause | Resolution |
|-------|-------|-----------|
| No rows returned | Wrong trace ID or outside time window | Increase `--hours`, confirm operation_Id |
| No invoke_agent spans found | Instrumentation disabled or different op name | Verify spans contain `gen_ai.operation.name=invoke_agent` |
| Evaluators fail | Missing Azure OpenAI creds | Set `AZURE_OPENAI_ENDPOINT` & `AZURE_OPENAI_API_KEY` |
| Events not verified | Ingestion delay | Re-run with larger `--hours` or more attempts |

### Extending Evaluations

* Add groundedness / factuality evaluators when available.
* Add RAG data source coverage metric (compare citations vs tool/data source IDs).
* Emit aggregate summary event (e.g., average score) for dashboards.
* Integrate pass/fail gating in CI by exiting nonzero when pass rate < threshold.

---
