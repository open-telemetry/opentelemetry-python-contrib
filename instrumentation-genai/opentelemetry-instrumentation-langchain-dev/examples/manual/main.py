import base64
import json
import os
from datetime import datetime, timedelta

import requests
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from opentelemetry import _events, _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.langchain import LangChainInstrumentor
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# configure tracing
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())
)

metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
metrics.set_meter_provider(MeterProvider(metric_readers=[metric_reader]))

# configure logging and events
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)
_events.set_event_logger_provider(EventLoggerProvider())


class TokenManager:
    def __init__(
        self, client_id, client_secret, app_key, cache_file=".token.json"
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.app_key = app_key
        self.cache_file = cache_file
        self.token_url = "https://id.cisco.com/oauth2/default/v1/token"

    def _get_cached_token(self):
        if not os.path.exists(self.cache_file):
            return None

        try:
            with open(self.cache_file, "r") as f:
                cache_data = json.load(f)

            expires_at = datetime.fromisoformat(cache_data["expires_at"])
            if datetime.now() < expires_at - timedelta(minutes=5):
                return cache_data["access_token"]
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return None

    def _fetch_new_token(self):
        payload = "grant_type=client_credentials"
        value = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("utf-8")
        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {value}",
        }

        response = requests.post(self.token_url, headers=headers, data=payload)
        response.raise_for_status()

        token_data = response.json()
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)

        cache_data = {
            "access_token": token_data["access_token"],
            "expires_at": expires_at.isoformat(),
        }

        with open(self.cache_file, "w") as f:
            json.dump(cache_data, f, indent=2)
        os.chmod(self.cache_file, 0o600)
        return token_data["access_token"]

    def get_token(self):
        token = self._get_cached_token()
        if token:
            return token
        return self._fetch_new_token()

    def cleanup_token_cache(self):
        if os.path.exists(self.cache_file):
            with open(self.cache_file, "r+b") as f:
                length = f.seek(0, 2)
                f.seek(0)
                f.write(b"\0" * length)
            os.remove(self.cache_file)


def main():
    # Set up instrumentation
    LangChainInstrumentor().instrument()

    import random

    # List of capital questions to randomly select from
    capital_questions = [
        "What is the capital of France?",
        "What is the capital of Germany?",
        "What is the capital of Italy?",
        "What is the capital of Spain?",
        "What is the capital of United Kingdom?",
        "What is the capital of Japan?",
        "What is the capital of Canada?",
        "What is the capital of Australia?",
        "What is the capital of Brazil?",
        "What is the capital of India?",
        "What is the capital of United States?",
    ]

    cisco_client_id = os.getenv("CISCO_CLIENT_ID")
    cisco_client_secret = os.getenv("CISCO_CLIENT_SECRET")
    cisco_app_key = os.getenv("CISCO_APP_KEY")

    token_manager = TokenManager(
        cisco_client_id, cisco_client_secret, cisco_app_key, "/tmp/.token.json"
    )

    api_key = token_manager.get_token()

    # Set up instrumentation once
    LangChainInstrumentor().instrument()

    # ChatOpenAI setup
    llm = ChatOpenAI(
        model="gpt-4.1",
        temperature=0.1,
        max_tokens=100,
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.5,
        stop_sequences=["\n", "Human:", "AI:"],
        seed=100,
        api_key=api_key,
        base_url="https://chat-ai.cisco.com/openai/deployments/gpt-4.1",
        default_headers={"api-key": api_key},
        model_kwargs={"user": '{"appkey": "' + cisco_app_key + '"}'},
    )

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = llm.invoke(messages)

    print("LLM output:\n", result)

    selected_question = random.choice(capital_questions)
    print(f"Selected question: {selected_question}")

    system_message = "You are a helpful assistant!"

    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=selected_question),
    ]

    result = llm.invoke(messages)
    print(f"LLM output: {result.content}")

    # Un-instrument after use
    LangChainInstrumentor().uninstrument()


if __name__ == "__main__":
    main()
