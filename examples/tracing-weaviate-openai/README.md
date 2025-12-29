# OpenTelemetry Tracing Example: Weaviate + OpenAI

This example demonstrates OpenTelemetry automatic instrumentation for Python applications using Weaviate vector database and OpenAI APIs, with traces visualized in Jaeger.

## Overview

The example showcases:
- **Zero-code instrumentation** using `opentelemetry-instrument` CLI
- **Unified traces** using Flask auto-instrumentation as the root span
- **Weaviate instrumentation** for vector database operations
- **OpenAI instrumentation** for embeddings and chat completions
- **HTTP instrumentation** for httpx and requests libraries
- **Jaeger** for trace visualization
- **Docker Compose** for easy deployment

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                       Docker Compose                               │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────────────┐ │
│  │   Jaeger    │  │  Weaviate   │  │           App             │ │
│  │             │  │             │  │                           │ │
│  │  UI: 16686  │  │  HTTP: 8080 │  │  Flask (port 5000)        │ │
│  │ OTLP: 4317  │  │  gRPC: 50051│  │  OpenAI + Weaviate + HTTP │ │
│  │             │  │             │  │  Auto-instrumented        │ │
│  └─────────────┘  └─────────────┘  └───────────────────────────┘ │
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
   cd examples/tracing-weaviate-openai
   docker compose up --build
   ```

3. **Run the demo:**
   Open http://localhost:5000/demo in your browser (or use curl)

4. **View traces in Jaeger:**
   Open http://localhost:16686 in your browser

5. **Select the service:**
   - Service: `weaviate-openai-demo`
   - Click "Find Traces"

## What the Demo Does

When you visit `/demo`, the application performs these traced operations all under a **single unified trace**:

1. **HTTP Requests** (demonstrating HTTP auto-instrumentation)
   - Makes requests using `requests` and `httpx` libraries
   - Each HTTP call appears as a child span

2. **Weaviate Collection Management**
   - Creates a collection called "Articles"
   - Deletes existing collection if present

3. **OpenAI Embeddings**
   - Generates embeddings for 5 sample articles
   - Uses `text-embedding-3-small` model

4. **Weaviate Data Operations**
   - Inserts articles with vector embeddings
   - Performs vector similarity search

5. **OpenAI Chat Completion**
   - Summarizes search results using GPT-4o-mini

## Viewing Unified Traces

The key feature of this example is **unified traces**. When you run the demo, you'll see a single trace with all operations as children of the Flask request:

```
GET /demo (Flask root span)
├── GET https://httpbin.org/get (requests)
├── GET https://httpbin.org/headers (httpx)
├── weaviate.collections.delete
├── weaviate.collections.create
├── embed text-embedding-3-small (OpenAI) x5
├── weaviate.data.insert x5
├── embed text-embedding-3-small (OpenAI) - query
├── weaviate.query.get
└── chat gpt-4o-mini (OpenAI)
```

Each span shows:
- Operation name and duration
- Database system (`weaviate`) and operation type
- Collection names
- OpenAI model and token usage
- HTTP method, URL, and status code

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Home page with links |
| `GET /demo` | Run the full demo workflow |
| `GET /health` | Health check endpoint |

## Configuration

Environment variables (set in docker-compose.yml):

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key | Required (from host env) |
| `WEAVIATE_URL` | Weaviate server URL | `http://weaviate:8080` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | `http://jaeger:4317` |
| `OTEL_SERVICE_NAME` | Service name in traces | `weaviate-openai-demo` |
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | Capture message content | `true` |
| `RUN_AS_SERVER` | Run as Flask server | `true` |

## Stopping the Demo

```bash
docker compose down
```

## How Unified Traces Work

This example achieves unified traces through **pure auto-instrumentation** (zero OpenTelemetry imports in application code):

1. **Flask auto-instrumentation** creates a root span for each HTTP request
2. All library calls within the request inherit the Flask span as their parent
3. The `opentelemetry-instrument` CLI enables all installed instrumentations automatically

This pattern is the recommended approach for achieving unified traces without manual instrumentation.

## Local Development (without Docker)

1. Install dependencies:
   ```bash
   pip install -e ../../opentelemetry-instrumentation
   pip install -e ../../opentelemetry-distro
   pip install -e ../../instrumentation-genai/opentelemetry-instrumentation-openai-v2
   pip install -e ../../instrumentation-genai/opentelemetry-instrumentation-weaviate
   pip install openai weaviate-client flask httpx requests opentelemetry-exporter-otlp-proto-grpc
   pip install opentelemetry-instrumentation-flask opentelemetry-instrumentation-httpx
   pip install opentelemetry-instrumentation-requests opentelemetry-instrumentation-urllib3
   ```

2. Start Jaeger and Weaviate manually

3. Run with auto-instrumentation:
   ```bash
   export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
   export OTEL_SERVICE_NAME=weaviate-openai-demo
   export WEAVIATE_URL=http://localhost:8080
   export RUN_AS_SERVER=true
   opentelemetry-instrument python app/main.py
   ```

4. Visit http://localhost:5000/demo

## Troubleshooting

**No traces appearing in Jaeger:**
- Ensure all services are running: `docker compose ps`
- Check app logs: `docker compose logs app`
- Verify OTLP endpoint is correct

**Weaviate connection errors:**
- Wait for Weaviate health check to pass
- Check Weaviate logs: `docker compose logs weaviate`

**OpenAI API errors:**
- Verify `OPENAI_API_KEY` is set correctly in your environment
- Check API key has sufficient credits

**Traces not unified:**
- Ensure you're accessing via `/demo` endpoint (Flask creates the root span)
- Direct script execution (`RUN_AS_SERVER=false`) will create separate traces
