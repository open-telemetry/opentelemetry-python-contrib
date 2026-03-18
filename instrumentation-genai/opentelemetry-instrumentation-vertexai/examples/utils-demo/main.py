# pylint: skip-file
"""
Combined agent lifecycle demo — create_agent + invoke_agent + metrics + events.

Combines automatic instrumentation (``VertexAIInstrumentor``) with manual
``TelemetryHandler`` spans from ``opentelemetry-util-genai`` to exercise
the full agent lifecycle:

1. Create a local LanggraphAgent  (``create_agent`` span)
2. Deploy it to Vertex AI Agent Engine  (``create_agent`` span)
3. Invoke the deployed agent  (``invoke_agent`` span, with auto-instrumented
   ``chat`` child span and metrics/events)
4. Cleanup — delete the deployed agent

Exports traces, metrics, and log-based events to a local OTLP collector.

Set environment variables before running::

    export GCP_PROJECT="your-project-id"       # required
    export GOOGLE_API_KEY="AIza..."            # optional, for google-genai LLM call
    python main.py
"""

import os
import time

import vertexai
from vertexai import agent_engines
from vertexai.generative_models import GenerativeModel

from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.util.genai.handler import TelemetryHandler
from opentelemetry.util.genai.types import AgentCreation, AgentInvocation

OTLP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
)
GCP_PROJECT = os.environ.get("GCP_PROJECT", "gcp-o11yinframon-nprd-81065")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
MODEL = "gemini-2.5-flash"
AGENT_NAME = "Currency Exchange Agent"


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


def setup_telemetry():
    """Configure OTel SDK: traces, metrics, logs/events → OTLP gRPC + console."""

    resource = Resource.create({"service.name": "genai-utils-demo"})

    # Traces — console + OTLP
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(ConsoleSpanExporter())
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)
        )
    )
    trace.set_tracer_provider(tracer_provider)

    # Metrics — OTLP
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True),
        export_interval_millis=5000,
    )
    meter_provider = MeterProvider(
        resource=resource, metric_readers=[metric_reader]
    )
    metrics.set_meter_provider(meter_provider)

    # Logs / Events — OTLP
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True)
        )
    )
    _logs.set_logger_provider(logger_provider)

    # Auto-instrument Vertex AI SDK calls (generate_content, etc.)
    VertexAIInstrumentor().instrument()

    return tracer_provider, meter_provider, logger_provider


def main():
    tracer_provider, meter_provider, logger_provider = setup_telemetry()
    handler = TelemetryHandler(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
    )

    staging_bucket = os.environ.get(
        "GCP_STAGING_BUCKET",
        f"gs://{GCP_PROJECT}-agent-staging",
    )
    vertexai.init(
        project=GCP_PROJECT,
        location=GCP_LOCATION,
        staging_bucket=staging_bucket,
    )
    server_address = f"{GCP_LOCATION}-aiplatform.googleapis.com"

    # ----- Step 1: Create local agent (create_agent span) -----
    print("\n[Step 1] Creating local LanggraphAgent...")
    with handler.create_agent(
        AgentCreation(
            agent_name=AGENT_NAME,
            provider="gcp_vertex_ai",
            request_model=MODEL,
            agent_description="Local LanggraphAgent for currency exchange",
            server_address=server_address,
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
    print(f"[Step 1] Local agent created: {AGENT_NAME}")

    # ----- Step 2: Deploy to Vertex AI Agent Engine (create_agent span) -----
    print("\n[Step 2] Deploying agent to Vertex AI Agent Engine...")
    print("         (this may take several minutes...)")
    with handler.create_agent(
        AgentCreation(
            agent_name=AGENT_NAME,
            provider="gcp_vertex_ai",
            request_model=MODEL,
            agent_description="Deploying agent to Vertex AI Agent Engine",
            server_address=server_address,
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
    print(f"[Step 2] Remote agent deployed: {remote_agent.resource_name}")

    # ----- Step 3: Invoke the agent (invoke_agent span) -----
    # Use GenerativeModel.generate_content() directly inside the invoke_agent
    # context so VertexAIInstrumentor auto-creates a `chat` child span.
    print("\n[Step 3] Invoking agent via generate_content...")
    model = GenerativeModel(MODEL)
    with handler.agent(
        AgentInvocation(
            agent_name=AGENT_NAME,
            provider="gcp_vertex_ai",
            request_model=MODEL,
            agent_description="Currency exchange agent demo",
            server_address=server_address,
        )
    ) as invocation:
        response = model.generate_content(
            "What is the exchange rate from US dollars to SEK today?"
        )
        # Populate response attributes from the model response
        usage = response.usage_metadata
        invocation.input_tokens = usage.prompt_token_count
        invocation.output_tokens = usage.candidates_token_count
        invocation.finish_reasons = ["stop"]

    print(f"[Step 3] Response:\n{response.text}\n")

    # ----- Step 4: Cleanup — delete the deployed agent -----
    try:
        print("[Step 4] Deleting remote agent...")
        remote_agent.delete(force=True)
        print("[Step 4] Done.")
    except Exception as exc:
        print(f"[Step 4] Cleanup failed — {type(exc).__name__}: {exc}")

    # ----- Flush telemetry -----
    print("\n[Flush] Waiting for telemetry export...")
    time.sleep(6)
    tracer_provider.force_flush()
    logger_provider.force_flush()
    print(
        "[Flush] Done! Check your collector for traces, metrics, and events."
    )


if __name__ == "__main__":
    main()
