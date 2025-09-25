from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import azure.identity
import openai
from agents import Agent, OpenAIChatCompletionsModel, Runner
from dotenv import load_dotenv

from opentelemetry import trace
from opentelemetry.instrumentation.openai_agents import (
    OpenAIAgentsInstrumentor,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

load_dotenv(override=True)

logging.basicConfig(level=logging.WARNING)


@dataclass
class _ApiConfig:
    """Container describing how to build the LLM client for the run."""

    build_client: Callable[[], openai.AsyncOpenAI]
    model_name: str
    base_url: str
    provider: str


def _set_capture_env(provider: str, base_url: str) -> None:
    """Opt into every GenAI content/metadata capture toggle."""

    capture_defaults = {
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT": "true",
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS": "true",
        "OTEL_GENAI_CAPTURE_MESSAGES": "true",
        "OTEL_GENAI_CAPTURE_SYSTEM_INSTRUCTIONS": "true",
        "OTEL_GENAI_CAPTURE_TOOL_DEFINITIONS": "true",
        "OTEL_GENAI_EMIT_OPERATION_DETAILS": "true",
        "OTEL_GENAI_AGENT_NAME": os.getenv(
            "OTEL_GENAI_AGENT_NAME", "Spanish Tutor Agent"
        ),
        "OTEL_GENAI_AGENT_DESCRIPTION": os.getenv(
            "OTEL_GENAI_AGENT_DESCRIPTION",
            "Conversational tutor that always replies in Spanish",
        ),
        "OTEL_GENAI_AGENT_ID": os.getenv(
            "OTEL_GENAI_AGENT_ID", "spanish-tutor"
        ),
    }
    for env_key, value in capture_defaults.items():
        os.environ.setdefault(env_key, value)

    parsed = urlparse(base_url)
    if parsed.hostname:
        os.environ.setdefault("OTEL_GENAI_SERVER_ADDRESS", parsed.hostname)
    if parsed.port:
        os.environ.setdefault("OTEL_GENAI_SERVER_PORT", str(parsed.port))


def _resolve_api_config() -> _ApiConfig:
    """Return the client factory/model for the configured API host."""

    host = os.getenv("API_HOST", "github").lower()

    if host == "github":
        base_url = os.getenv(
            "GITHUB_OPENAI_BASE_URL",
            "https://models.inference.ai.azure.com",
        ).rstrip("/")
        model_name = os.getenv("GITHUB_MODEL", "gpt-4o")
        api_key = os.environ["GITHUB_TOKEN"]

        def _build_client() -> openai.AsyncOpenAI:
            return openai.AsyncOpenAI(base_url=base_url, api_key=api_key)

        return _ApiConfig(
            build_client=_build_client,
            model_name=model_name,
            base_url=base_url,
            provider="azure.ai.inference",
        )

    if host == "azure":
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        api_version = os.environ["AZURE_OPENAI_VERSION"]
        deployment = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]

        credential = azure.identity.DefaultAzureCredential()
        token_provider = azure.identity.get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default",
        )

        def _build_client() -> openai.AsyncAzureOpenAI:
            return openai.AsyncAzureOpenAI(
                api_version=api_version,
                azure_endpoint=endpoint,
                azure_ad_token_provider=token_provider,
            )

        return _ApiConfig(
            build_client=_build_client,
            model_name=deployment,
            base_url=endpoint,
            provider="azure.ai.openai",
        )

    if host == "ollama":
        base_url = os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434/v1"
        ).rstrip("/")
        model_name = os.getenv("OLLAMA_MODEL", "llama3.1:latest")
        api_key = os.getenv("OLLAMA_API_KEY", "none")

        def _build_client() -> openai.AsyncOpenAI:
            return openai.AsyncOpenAI(base_url=base_url, api_key=api_key)

        return _ApiConfig(
            build_client=_build_client,
            model_name=model_name,
            base_url=base_url,
            provider="self.hosted",
        )

    raise ValueError(f"Unsupported API_HOST '{host}'")


def _configure_otel() -> None:
    """Configure OpenTelemetry with Azure Monitor or console export."""

    conn = os.getenv("APPLICATION_INSIGHTS_CONNECTION_STRING")
    resource = Resource.create(
        {
            "service.name": "spanish-tutor-app",
            "service.namespace": "language-learning",
            "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
        }
    )

    tracer_provider = TracerProvider(resource=resource)

    if conn:
        try:
            from azure.monitor.opentelemetry.exporter import (  # type: ignore import-not-found
                AzureMonitorTraceExporter,
            )
        except ImportError:  # pragma: no cover - optional dependency
            print(
                "Warning: Azure Monitor exporter not installed. "
                "Install with: pip install azure-monitor-opentelemetry-exporter",
            )
            tracer_provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )
        else:
            tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    AzureMonitorTraceExporter.from_connection_string(conn)
                )
            )
            print("[otel] Azure Monitor trace exporter configured")
    else:
        tracer_provider.add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter())
        )
        print("[otel] Console span exporter configured")
        print(
            "[otel] Set APPLICATION_INSIGHTS_CONNECTION_STRING to export to "
            "Application Insights instead of the console",
        )

    trace.set_tracer_provider(tracer_provider)


api_config = _resolve_api_config()
_set_capture_env(api_config.provider, api_config.base_url)
_configure_otel()

# Instrument OpenAI Agents using the configured tracer provider
OpenAIAgentsInstrumentor().instrument(
    tracer_provider=trace.get_tracer_provider()
)

client = api_config.build_client()

agent = Agent(
    name="Spanish tutor",
    instructions="You are a Spanish tutor. Help the user learn Spanish. ONLY respond in Spanish.",
    model=OpenAIChatCompletionsModel(
        model=api_config.model_name, openai_client=client
    ),
)


def _infer_span_name(provider: str) -> str:
    return f"spanish_tutor_session[{provider}]"


async def main() -> None:
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(_infer_span_name(api_config.provider)):
        result = await Runner.run(agent, input="hi how are you?")
        print(result.final_output)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        trace.get_tracer_provider().shutdown()
