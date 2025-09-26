from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import azure.identity
import openai
from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool
from agents.extensions.visualization import draw_graph
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
    """Helper structure for creating the OpenAI client."""

    build_client: Callable[[], openai.AsyncOpenAI]
    model_name: str
    base_url: str
    provider: str


def _set_capture_env(provider: str, base_url: str) -> None:
    """Enable all GenAI capture flags before instrumentation runs."""

    capture_defaults = {
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT": "true",
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS": "true",
        "OTEL_GENAI_CAPTURE_MESSAGES": "true",
        "OTEL_GENAI_CAPTURE_SYSTEM_INSTRUCTIONS": "true",
        "OTEL_GENAI_CAPTURE_TOOL_DEFINITIONS": "true",
        "OTEL_GENAI_EMIT_OPERATION_DETAILS": "true",
        "OTEL_GENAI_AGENT_NAME": os.getenv(
            "OTEL_GENAI_AGENT_NAME", "Weather Orchestration Service"
        ),
        "OTEL_GENAI_AGENT_DESCRIPTION": os.getenv(
            "OTEL_GENAI_AGENT_DESCRIPTION",
            "Multi-agent weather service routing requests to language-specific forecasters",
        ),
        "OTEL_GENAI_AGENT_ID": os.getenv(
            "OTEL_GENAI_AGENT_ID", "weather-orchestrator"
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
    """Create the Async OpenAI client builder for the configured host."""

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
    """Configure OpenTelemetry exporters and tracer provider."""

    conn = os.getenv("APPLICATION_INSIGHTS_CONNECTION_STRING")
    resource = Resource.create(
        {
            "service.name": "multi-agent-weather-service",
            "service.namespace": "weather-orchestration",
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

OpenAIAgentsInstrumentor().instrument(
    tracer_provider=trace.get_tracer_provider()
)

client = api_config.build_client()


@function_tool
def get_weather(city: str) -> dict[str, object]:
    return {
        "city": city,
        "temperature": 72,
        "description": "Sunny",
    }


spanish_agent = Agent(
    name="Spanish agent",
    instructions="You only speak Spanish.",
    tools=[get_weather],
    model=OpenAIChatCompletionsModel(
        model=api_config.model_name, openai_client=client
    ),
)

english_agent = Agent(
    name="English agent",
    instructions="You only speak English.",
    tools=[get_weather],
    model=OpenAIChatCompletionsModel(
        model=api_config.model_name, openai_client=client
    ),
)

triage_agent = Agent(
    name="Triage agent",
    instructions="Handoff to the appropriate agent based on the language of the request.",
    handoffs=[spanish_agent, english_agent],
    model=OpenAIChatCompletionsModel(
        model=api_config.model_name, openai_client=client
    ),
)


def _root_span_name(provider: str) -> str:
    return f"weather_service_request[{provider}]"


async def main() -> None:
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(
        _root_span_name(api_config.provider)
    ) as span:
        user_request = (
            "Hola, ¿cómo estás? ¿Puedes darme el clima para San Francisco CA?"
        )

        span.set_attribute("user.request", user_request)
        span.set_attribute("api.host", os.getenv("API_HOST", "github"))
        span.set_attribute("model.name", api_config.model_name)

        try:
            result = await Runner.run(triage_agent, input=user_request)
            print(result.final_output)

            span.set_attribute(
                "agent.response",
                result.final_output[:500] if result.final_output else "",
            )
            span.set_attribute("request.success", True)
        except Exception as exc:  # pragma: no cover - defensive logging
            span.record_exception(exc)
            span.set_attribute("request.success", False)
            raise


if __name__ == "__main__":
    try:
        draw_graph(triage_agent)
        asyncio.run(main())
    finally:
        trace.get_tracer_provider().shutdown()
