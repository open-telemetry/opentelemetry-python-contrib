# Multi-Agent Travel Planning (OpenAI Agents + OpenTelemetry)

This folder now contains **two** illustrative examples of instrumented multi-agent travel planning using the OpenAI Agents API and OpenTelemetry:

1. `multi_travel_planner.py` – A concise, faster single-agent orchestration that chains a few simple function tools (geocode / weather / cuisine). Good for a quick look at instrumentation wiring and a minimal trace.
2. `enhanced.py` – A richer, production-style multi‑agent workflow that mirrors a LangGraph style handoff pipeline (Coordinator → Flight → Hotel → Activity → Budget → Plan Synthesizer). It demonstrates structured outputs, tool usage, deterministic handoffs, OpenTelemetry spans, and interactive fallbacks when the model asks clarifying questions.

---
## Why the Enhanced Version?

`enhanced.py` showcases patterns often needed in real systems:

* Multiple cooperating specialist agents with explicit handoff definitions.
* Structured extraction via Pydantic (`TripDetails`, `FlightRecommendation`, etc.).
* Automatic tracing of each agent invocation and tool execution via `opentelemetry-instrumentation-openai-agents`.
* A resilient trip detail parsing layer (JSON parsing + heuristic extraction) and an **interactive fallback prompt flow** (so a model asking for missing info doesn’t crash the pipeline).
* Budget analysis + synthesis phase to create a cohesive final plan.
* Per‑agent model instances (can vary temperature / deployment) while retaining a single end‑to‑end workflow trace.

---
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

---
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
