# OpenTelemetry Tracing Example: LangChain + LangGraph + OpenAI

This example demonstrates OpenTelemetry automatic instrumentation for Python applications using LangChain, LangGraph, and OpenAI, with traces visualized in Jaeger.

## Overview

The example showcases:
- **Zero-code instrumentation** using `opentelemetry-instrument` CLI
- **Unified traces** using Flask auto-instrumentation as the root span
- **LangChain instrumentation** for LLM calls, tools, and agent operations
- **LangGraph instrumentation** for workflow executions
- **OpenAI instrumentation** for chat completions
- **ReAct Agent** with custom tools (weather, calculator, knowledge base)
- **Jaeger** for trace visualization
- **Docker Compose** for easy deployment

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                       Docker Compose                               │
│  ┌─────────────┐  ┌───────────────────────────────────────────┐  │
│  │   Jaeger    │  │                  App                       │  │
│  │             │  │                                            │  │
│  │  UI: 16686  │  │  Flask (port 5000)                         │  │
│  │ OTLP: 4317  │  │  LangChain + LangGraph + OpenAI            │  │
│  │             │  │  Auto-instrumented (zero-code)             │  │
│  └─────────────┘  └───────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Docker and Docker Compose
- OpenAI API key (set as environment variable)

## Quick Start

1. **Set your OpenAI API key:**
   ```bash
   export OPENAI_API_KEY=your-api-key-here
   ```

2. **Start the services:**
   ```bash
   cd examples/tracing-langchain-openai
   docker compose up --build
   ```

3. **Run the demo:**
   Open http://localhost:5000/demo in your browser (or use curl)

4. **View traces in Jaeger:**
   Open http://localhost:16686 in your browser

5. **Select the service:**
   - Service: `langchain-openai-demo`
   - Click "Find Traces"

## What the Demo Does

When you visit `/demo`, the application runs several traced scenarios:

### Demo 1: Weather Query
- Agent uses the `get_weather` tool to fetch weather for multiple cities
- Shows tool calling and multi-step reasoning

### Demo 2: Calculation Query
- Agent uses the `calculate` tool for math operations
- Demonstrates safe expression evaluation

### Demo 3: Knowledge Base Query
- Agent uses `search_knowledge_base` tool
- Retrieves information about Python, OpenTelemetry, LangChain, etc.

### Demo 4: Multi-Tool Workflow
- LangGraph workflow orchestrating multiple tool calls
- Combines weather, calculation, and knowledge base queries
- Shows stateful workflow execution

## Custom Tools

The example includes three custom tools:

| Tool | Description |
|------|-------------|
| `get_weather(city)` | Returns mock weather data for a city |
| `calculate(expression)` | Evaluates mathematical expressions safely |
| `search_knowledge_base(query)` | Searches a mock knowledge base |

## Viewing Unified Traces

The key feature of this example is **unified traces**. When you run the demo, you'll see traces with hierarchical spans:

```
GET /demo (Flask root span)
├── LangGraph workflow
│   ├── agent node
│   │   ├── LangChain LLM call
│   │   │   └── OpenAI chat completion
│   │   └── tool execution
│   └── final node
├── LangGraph workflow (next query)
│   └── ...
```

Each span shows:
- Operation name and duration
- LLM model and token usage
- Tool names and inputs/outputs
- Workflow state transitions
- Error details (if any)

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Home page with links |
| `GET /demo` | Run all demo scenarios |
| `GET /agent` | Run a single agent query |
| `GET /workflow` | Run a single workflow query |
| `GET /health` | Health check endpoint |

## Configuration

Environment variables (set in docker-compose.yml):

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key | Required (from host env) |
| `OPENAI_MODEL` | OpenAI model to use | `gpt-4o-mini` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | `http://jaeger:4317` |
| `OTEL_SERVICE_NAME` | Service name in traces | `langchain-openai-demo` |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Capture message content | `true` |

## Stopping the Demo

```bash
docker compose down
```

## How Zero-Code Instrumentation Works

This example uses **pure auto-instrumentation** (no OpenTelemetry imports in application code):

1. **Flask auto-instrumentation** creates a root span for each HTTP request
2. **LangChain instrumentation** traces all LLM calls, tool executions, and agent operations
3. **LangGraph instrumentation** traces workflow executions and state transitions
4. **OpenAI instrumentation** traces the underlying API calls
5. The `opentelemetry-instrument` CLI enables all installed instrumentations automatically

All library calls within a request inherit the Flask span as their parent, creating unified traces.

## Local Development (without Docker)

1. Install dependencies:
   ```bash
   pip install -e ../../opentelemetry-instrumentation
   pip install -e ../../opentelemetry-distro
   pip install -e ../../instrumentation-genai/opentelemetry-instrumentation-openai-v2
   pip install -e ../../instrumentation-genai/opentelemetry-instrumentation-langchain
   pip install -e ../../instrumentation-genai/opentelemetry-instrumentation-langgraph
   pip install langchain langchain-openai langgraph flask
   pip install opentelemetry-exporter-otlp-proto-grpc
   pip install opentelemetry-instrumentation-flask
   ```

2. Start Jaeger manually:
   ```bash
   docker run -d --name jaeger \
     -e COLLECTOR_OTLP_ENABLED=true \
     -p 16686:16686 \
     -p 4317:4317 \
     jaegertracing/all-in-one:latest
   ```

3. Run with auto-instrumentation:
   ```bash
   export OPENAI_API_KEY=your-api-key
   export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
   export OTEL_SERVICE_NAME=langchain-openai-demo
   opentelemetry-instrument python app/main.py
   ```

4. Visit http://localhost:5000/demo

## Troubleshooting

**No traces appearing in Jaeger:**
- Ensure all services are running: `docker compose ps`
- Check app logs: `docker compose logs app`
- Verify OTLP endpoint is correct

**OpenAI API errors:**
- Verify `OPENAI_API_KEY` is set correctly in your environment
- Check API key has sufficient credits
- Try a different model with `OPENAI_MODEL=gpt-3.5-turbo`

**Traces not unified:**
- Ensure you're accessing via Flask endpoints (creates the root span)
- Check that all instrumentations are installed and enabled

**Tool execution errors:**
- Check the application logs for detailed error messages
- Verify the tools are properly defined with correct type hints
