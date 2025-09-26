"""Weather lookup chatbot with full GenAI telemetry capture."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

import azure.identity
import openai
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
    """Helper describing how to construct the OpenAI client."""

    build_client: Callable[[], openai.OpenAI]
    model_name: str
    base_url: str
    provider: str


def _set_capture_env(provider: str, base_url: str) -> None:
    """Enable all GenAI capture toggles before instrumentation hooks."""

    capture_defaults = {
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT": "true",
        "OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS": "true",
        "OTEL_GENAI_CAPTURE_MESSAGES": "true",
        "OTEL_GENAI_CAPTURE_SYSTEM_INSTRUCTIONS": "true",
        "OTEL_GENAI_CAPTURE_TOOL_DEFINITIONS": "true",
        "OTEL_GENAI_EMIT_OPERATION_DETAILS": "true",
        "OTEL_GENAI_AGENT_NAME": os.getenv(
            "OTEL_GENAI_AGENT_NAME", "Weather Chatbot"
        ),
        "OTEL_GENAI_AGENT_DESCRIPTION": os.getenv(
            "OTEL_GENAI_AGENT_DESCRIPTION",
            "Single-agent weather assistant that demonstrates tool calling",
        ),
        "OTEL_GENAI_AGENT_ID": os.getenv(
            "OTEL_GENAI_AGENT_ID", "weather-chatbot"
        ),
    }
    for key, value in capture_defaults.items():
        os.environ.setdefault(key, value)

    parsed = urlparse(base_url)
    if parsed.hostname:
        os.environ.setdefault("OTEL_GENAI_SERVER_ADDRESS", parsed.hostname)
    if parsed.port:
        os.environ.setdefault("OTEL_GENAI_SERVER_PORT", str(parsed.port))


def _resolve_api_config() -> _ApiConfig:
    """Return synchronous client configuration for the selected host."""

    host = os.getenv("API_HOST", "github").lower()

    if host == "github":
        base_url = os.getenv(
            "GITHUB_OPENAI_BASE_URL",
            "https://models.inference.ai.azure.com",
        ).rstrip("/")
        model_name = os.getenv("GITHUB_MODEL", "gpt-4o")
        api_key = os.environ["GITHUB_TOKEN"]

        def _build_client() -> openai.OpenAI:
            return openai.OpenAI(base_url=base_url, api_key=api_key)

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

        def _build_client() -> openai.AzureOpenAI:
            return openai.AzureOpenAI(
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

    raise ValueError(f"Unsupported API_HOST '{host}'")


def _configure_otel() -> None:
    """Configure tracer provider and exporters."""

    conn = os.getenv("APPLICATION_INSIGHTS_CONNECTION_STRING")
    resource = Resource.create(
        {
            "service.name": "weather-chatbot-service",
            "service.namespace": "weather-lookup",
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


def main() -> None:
    api_config = _resolve_api_config()
    _set_capture_env(api_config.provider, api_config.base_url)
    _configure_otel()

    OpenAIAgentsInstrumentor().instrument(
        tracer_provider=trace.get_tracer_provider()
    )

    client = api_config.build_client()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup_weather",
                "description": "Lookup the weather for a given city name or zip code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city_name": {
                            "type": "string",
                            "description": "The city name",
                        },
                        "zip_code": {
                            "type": "string",
                            "description": "The zip code",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        }
    ]

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(
        f"weather_lookup_request[{api_config.provider}]"
    ) as span:
        user_query = "what is the weather in NYC?"

        span.set_attribute("user.query", user_query)
        span.set_attribute("api.host", os.getenv("API_HOST", "github"))
        span.set_attribute("model.name", api_config.model_name)
        span.set_attribute("tool.count", len(tools))
        span.set_attribute(
            "tool.names", [t["function"]["name"] for t in tools]
        )

        try:
            response = client.chat.completions.create(
                model=api_config.model_name,
                messages=[
                    {"role": "system", "content": "You're a weather chatbot"},
                    {"role": "user", "content": user_query},
                ],
                tools=tools,
            )

            print(
                f"Response from {api_config.model_name} on {os.getenv('API_HOST', 'github')}:\n"
            )

            tool_calls = response.choices[0].message.tool_calls or []
            for index, message in enumerate(tool_calls):
                print(message.function.name)
                print(message.function.arguments)
                span.set_attribute(
                    f"tool_call.{index}.name", message.function.name
                )
                span.set_attribute(
                    f"tool_call.{index}.arguments", message.function.arguments
                )
            span.set_attribute("tool_calls.count", len(tool_calls))
            span.set_attribute("request.success", True)

        except Exception as exc:  # pragma: no cover - defensive logging
            span.record_exception(exc)
            span.set_attribute("request.success", False)
            print(f"Error: {exc}")
            raise

    trace.get_tracer_provider().shutdown()


if __name__ == "__main__":
    main()
