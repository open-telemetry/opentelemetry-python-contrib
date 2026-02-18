# OpenAI Agents Content Capture Demo

This example exercises the `OpenAIAgentsInstrumentor` with message content
capture enabled, illustrating how prompts, responses, and tool payloads are
recorded on spans and span events.

> The demo uses the local tracing utilities from the `openai-agents`
> package—no outbound API calls are made.

## Prerequisites

1. Activate the repository virtual environment:

   ```bash
   source ../../.venv/bin/activate
   ```

2. Copy `.env.example` to `.env` and provide any overrides you need (for example,
   setting `OTEL_EXPORTER_OTLP_ENDPOINT`).
3. Ensure `openai-agents` is installed in the environment (it is included in
   the shared development venv for this repository).

## Run the demo

```bash
python main.py
```

The script will:

- Configure the OpenTelemetry SDK with an OTLP exporter so spans reach your collector.
- Instrument the OpenAI Agents tracing hooks with content capture enabled.
- Simulate an agent invocation that performs a generation and a tool call.
- Print the resulting spans, attributes, and events (including JSON-encoded
  prompts and responses) to stdout.

## Customisation tips

- Set `OTEL_SERVICE_NAME` before running to override the default service name.
- Adjust the OTLP exporter configuration (endpoint, protocol) through `.env`.
- Modify the prompts, tool payloads, or add additional spans in `run_workflow`
  to explore different content capture scenarios.
