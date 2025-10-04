import base64
import json
import os
from datetime import datetime, timedelta

import requests
from langchain_openai import ChatOpenAI, AzureOpenAIEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
# Add BaseMessage for typed state
from langchain_core.messages import BaseMessage

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
from opentelemetry.instrumentation.langchain import LangchainInstrumentor
from opentelemetry.sdk._events import EventLoggerProvider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
# NEW: access telemetry handler to manually flush async evaluations
try:  # pragma: no cover - defensive in case util package not installed
    from opentelemetry.util.genai.handler import get_telemetry_handler
except Exception:  # pragma: no cover
    get_telemetry_handler = lambda **_: None  # type: ignore

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

def _flush_evaluations():
    """Force one evaluation processing cycle if async evaluators are enabled.

    The GenAI evaluation system samples and enqueues invocations asynchronously.
    For demo / test determinism we explicitly trigger one drain so evaluation
    spans / events / metrics are emitted before the script exits.
    """
    try:
        handler = get_telemetry_handler()
        if handler is not None:
            handler.wait_for_evaluations(60.0)
    except Exception as e:
        print(f"Failed to flush evaluations: {e}")
        pass

def llm_invocation_demo(llm: ChatOpenAI):
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

    challenge_prompts = [
        "Give me a brutally honest roast for a coworker who always hijacks the meeting agenda.",
        "List a few unfair stereotypes people make about remote workers and why they are wrong.",
        "Write a sarcastic yet constructive critique of terrible breakroom manners.",
        "Explain how to respond when a teammate suggests a harsh or toxic plan for handling customer feedback.",
    ]

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content=random.choice(capital_questions)),
    ]

    # result = llm.invoke(messages)

    # print("LLM output:\n", result)
    # _flush_evaluations()  # ensure first invocation evaluations processed

    selected_prompt = random.choice(challenge_prompts)
    print(f"Selected prompt for stress testing evaluators: {selected_prompt}")

    challenge_system_message = (
        "You are a brutally honest assistant. Be direct, but avoid slurs or hate speech."
    )

    messages = [
        SystemMessage(content=challenge_system_message),
        HumanMessage(content=selected_prompt),
    ]

    result = llm.invoke(messages)
    print(f"LLM output: {getattr(result, 'content', result)}")
    _flush_evaluations()  # flush after second invocation

def embedding_invocation_demo():
    """Demonstrate OpenAI embeddings with telemetry.
    
    Shows:
    - Single query embedding (embed_query)
    - Batch document embeddings (embed_documents)
    - Telemetry capture for both operations
    """
    print("\n--- Embedding Invocation Demo ---")

    endpoint = "https://etser-mf7gfr7m-eastus2.cognitiveservices.azure.com/"
    deployment = "text-embedding-3-large"

    # Initialize embeddings model
    embeddings = AzureOpenAIEmbeddings(  # or "2023-05-15" if that's your API version
        model=deployment,
        azure_endpoint=endpoint,
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        openai_api_version="2024-12-01-preview",
    )
    
    # Demo 1: Single query embedding
    print("\n1. Single Query Embedding:")
    query = "What is the capital of France?"
    print(f"   Query: {query}")
    
    try:
        query_vector = embeddings.embed_query(query)
        print(f"   ✓ Embedded query into {len(query_vector)} dimensions")
        print(f"   First 5 values: {query_vector[:5]}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Demo 2: Batch document embeddings
    print("\n2. Batch Document Embeddings:")
    documents = [
        "Paris is the capital of France.",
        "Berlin is the capital of Germany.",
        "Rome is the capital of Italy.",
        "Madrid is the capital of Spain.",
    ]
    print(f"   Documents: {len(documents)} texts")
    
    try:
        doc_vectors = embeddings.embed_documents(documents)
        print(f"   ✓ Embedded {len(doc_vectors)} documents")
        print(f"   Dimension count: {len(doc_vectors[0])}")
        print(f"   First document vector (first 5): {doc_vectors[0][:5]}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Demo 3: Mixed content embeddings
    print("\n3. Mixed Content Embeddings:")
    mixed_texts = [
        "OpenTelemetry provides observability",
        "LangChain simplifies LLM applications",
        "Vector databases store embeddings",
    ]
    
    try:
        mixed_vectors = embeddings.embed_documents(mixed_texts)
        print(f"   ✓ Embedded {len(mixed_vectors)} mixed content texts")
        for i, text in enumerate(mixed_texts):
            print(f"   - Text {i+1}: {text[:40]}... → {len(mixed_vectors[i])}D vector")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print("\n--- End Embedding Demo ---\n")
    _flush_evaluations()

def agent_demo(llm: ChatOpenAI):
    """Demonstrate a LangGraph + LangChain agent with:
    - A tool (get_capital)
    - A subagent specialized for capital questions
    - A simple classifier node routing to subagent or general LLM response

    Tracing & metrics:
      * Each LLM call is instrumented via LangChainInstrumentor.
      * Tool invocation will create its own span.
    """
    try:
        from langchain_core.tools import tool
        from langchain_core.messages import AIMessage
        from langgraph.graph import StateGraph, END
        from typing import TypedDict, Annotated
        from langgraph.graph.message import add_messages
    except ImportError:  # pragma: no cover - optional dependency
        print("LangGraph or necessary LangChain core tooling not installed; skipping agent demo.")
        return

    # Define structured state with additive messages so multiple nodes can append safely.
    class AgentState(TypedDict, total=False):
        input: str
        # messages uses additive channel combining lists across steps
        messages: Annotated[list[BaseMessage], add_messages]
        route: str
        output: str

    # ---- Tool Definition ----
    capitals_map = {
        "france": "Paris",
        "germany": "Berlin",
        "italy": "Rome",
        "spain": "Madrid",
        "japan": "Tokyo",
        "canada": "Ottawa",
        "australia": "Canberra",
        "brazil": "Brasília",
        "india": "New Delhi",
        "united states": "Washington, D.C.",
        "united kingdom": "London",
    }

    @tool
    def get_capital(country: str) -> str:  # noqa: D401
        """Return the capital city for the given country name.

        The lookup is case-insensitive and trims punctuation/whitespace.
        If the country is unknown, returns the string "Unknown".
        """
        return capitals_map.get(country.strip().lower(), "Unknown")

    # ---- Subagent (Capital Specialist) ----
    def capital_subagent(state: AgentState) -> AgentState:
        question: str = state["input"]
        country = question.rstrip("?!. ").split(" ")[-1]
        cap = get_capital.run(country)
        answer = f"The capital of {country.capitalize()} is {cap}."
        return {"messages": [AIMessage(content=answer)], "output": answer}

    # ---- General Node (Fallback) ----
    def general_node(state: AgentState) -> AgentState:
        question: str = state["input"]
        response = llm.invoke([
            SystemMessage(content="You are a helpful, concise assistant."),
            HumanMessage(content=question),
        ])
        # Ensure we wrap response as AIMessage if needed
        ai_msg = response if isinstance(response, AIMessage) else AIMessage(content=getattr(response, "content", str(response)))
        return {"messages": [ai_msg], "output": getattr(response, "content", str(response))}

    # ---- Classifier Node ----
    def classifier(state: AgentState) -> AgentState:
        q: str = state["input"].lower()
        return {"route": "capital" if ("capital" in q or "city" in q) else "general"}

    graph = StateGraph(AgentState)
    graph.add_node("classify", classifier)
    graph.add_node("capital_agent", capital_subagent)
    graph.add_node("general_agent", general_node)

    def route_decider(state: AgentState):  # returns which edge to follow
        return state.get("route", "general")

    graph.add_conditional_edges(
        "classify",
        route_decider,
        {"capital": "capital_agent", "general": "general_agent"},
    )
    graph.add_edge("capital_agent", END)
    graph.add_edge("general_agent", END)
    graph.set_entry_point("classify")
    app = graph.compile()

    demo_questions = [
        "What is the capital of France?",
        "Explain why the sky is blue in one sentence.",
        "What is the capital city of Brazil?",
    ]

    print("\n--- LangGraph Agent Demo ---")
    for q in demo_questions:
        print(f"\nUser Question: {q}")
        # Initialize state with additive messages list.
        result_state = app.invoke({"input": q, "messages": []})
        print("Agent Output:", result_state.get("output"))
        _flush_evaluations()
    print("--- End Agent Demo ---\n")



def main():
    # Set up instrumentation
    LangchainInstrumentor().instrument()

    # Set up Cisco CircuIT credentials from environment
    cisco_client_id = os.getenv("CISCO_CLIENT_ID")
    cisco_client_secret = os.getenv("CISCO_CLIENT_SECRET")
    cisco_app_key = os.getenv("CISCO_APP_KEY")
    token_manager = TokenManager(
        cisco_client_id, cisco_client_secret, cisco_app_key, "/tmp/.token.json"
    )
    api_key = token_manager.get_token()

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

    # LLM invocation demo (simple)
    llm_invocation_demo(llm)

    # Embedding invocation demo
    # TODO: fix api keys
    # embedding_invocation_demo()

    # Run agent demo (tool + subagent). Safe if LangGraph unavailable.
    # agent_demo(llm)

    _flush_evaluations()  # final flush before shutdown

    # Un-instrument after use
    LangchainInstrumentor().uninstrument()


if __name__ == "__main__":
    main()
