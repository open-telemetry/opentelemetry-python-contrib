# pylint: skip-file
"""
Vertex AI Agent Engine — create_agent instrumentation demo.

Combines automatic instrumentation (``VertexAIInstrumentor``) with
manual ``TelemetryHandler.create_agent()`` spans from
``opentelemetry-util-genai`` to show how genai-utils extends the
existing Vertex AI instrumentation with agent lifecycle spans.

Also demonstrates deploying an agent to Vertex AI Agent Engine
via ``agent_engines.create()`` (requires GCP project + ADC).

Set environment variables before running:

    export GOOGLE_API_KEY="AIza..."
    export GCP_PROJECT="your-project-id"
    python main.py
"""

import os

import vertexai
from google import genai
from vertexai import agent_engines

# NOTE: OpenTelemetry Python Logs and Events APIs are in beta
from opentelemetry import _logs, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import AgentCreation

OTLP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
)
GCP_PROJECT = os.environ.get("GCP_PROJECT", "gcp-o11yinframon-nprd-81065")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
MODEL = "gemini-2.5-flash"
AGENT_NAME = "Currency Exchange Agent"

# configure tracing
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(ConsoleSpanExporter())
)
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)

# configure logging and events
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(
        OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True)
    )
)

# Auto-instrument Vertex AI SDK calls (generate_content, etc.)
VertexAIInstrumentor().instrument()


def get_exchange_rate(
    currency_from: str = "USD",
    currency_to: str = "EUR",
    currency_date: str = "latest",
) -> dict:
    """Retrieves the exchange rate between two currencies on a specified date."""
    import requests  # noqa: PLC0415

    response = requests.get(
        f"https://api.frankfurter.app/{currency_date}",
        params={"from": currency_from, "to": currency_to},
    )
    return response.json()


def main():
    # Initialize Vertex AI (needed for LanggraphAgent)
    staging_bucket = os.environ.get(
        "GCP_STAGING_BUCKET",
        f"gs://{GCP_PROJECT}-agent-staging",
    )
    vertexai.init(
        project=GCP_PROJECT,
        location=GCP_LOCATION,
        staging_bucket=staging_bucket,
    )
    # API-key client for LLM calls (uses GOOGLE_API_KEY env var)
    client = genai.Client()
    handler = TelemetryHandler()

    # ----- Step 1: LLM call via google-genai SDK -----
    print("[LLM call] Generating content...")
    response = client.models.generate_content(
        model=MODEL,
        contents="Write a short poem on OpenTelemetry.",
    )
    print(f"[LLM call] Response:\n{response.text}\n")

    # ----- Step 2: Create local agent (create_agent span) -----
    with handler.create_agent(
        AgentCreation(
            name=AGENT_NAME,
            provider="gcp_vertex_ai",
            request_model=MODEL,
            description="Local LanggraphAgent for currency exchange",
            server_address=f"{GCP_LOCATION}-aiplatform.googleapis.com",
        )
    ) as _creation:
        agent = agent_engines.LanggraphAgent(
            model=MODEL,
            tools=[get_exchange_rate],
            model_kwargs={
                "temperature": 0.28,
                "max_output_tokens": 1000,
                "top_p": 0.95,
            },
        )
        print(f"[create_agent] Local agent created: {AGENT_NAME}")

    # ----- Step 3: Deploy to Vertex AI Agent Engine (create_agent span) -----
    print("\n[deploy] Deploying agent to Vertex AI Agent Engine...")
    print("         (this may take several minutes...)")
    with handler.create_agent(
        AgentCreation(
            name=AGENT_NAME,
            provider="gcp_vertex_ai",
            request_model=MODEL,
            description="Deploying agent to Vertex AI Agent Engine",
            server_address=f"{GCP_LOCATION}-aiplatform.googleapis.com",
        )
    ) as _deploy_creation:
        remote_agent = agent_engines.create(
            agent_engine=agent,
            display_name=AGENT_NAME,
            requirements=[
                "google-cloud-aiplatform[agent_engines,langchain]",
                "langchain-google-vertexai",
            ],
        )
        print(f"[deploy] Remote agent deployed: {remote_agent.resource_name}")

    # ----- Step 4: Query the remote agent -----
    try:
        print("\n[query] Querying remote agent...")
        query_response = remote_agent.query(
            input={
                "messages": [
                    (
                        "user",
                        "What is the exchange rate from US dollars to SEK today?",
                    ),
                ]
            }
        )
        print(f"[query] Response: {query_response}\n")
    except Exception as exc:
        print(f"\n[query] Failed — {type(exc).__name__}: {exc}\n")
    finally:
        # ----- Cleanup: delete the deployed agent -----
        print("[cleanup] Deleting remote agent...")
        remote_agent.delete(force=True)
        print("[cleanup] Done.")


if __name__ == "__main__":
    main()
