import base64
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any, List, TypedDict

import requests
import weaviate
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

# LangChain callback imports
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.outputs import LLMResult
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

# OpenTelemetry imports
from opentelemetry import _logs as logs
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    OTLPLogExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# GenAI Utils imports
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    AgentInvocation as Agent,
)
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Task,
    Text,
    Workflow,
)

load_dotenv()


# Cisco Token Manager
class TokenManager:
    def __init__(
        self,
        client_id,
        client_secret,
        app_key,
        cache_file="/tmp/cisco_token_cache.json",
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

        # Create file with secure permissions (owner read/write only)
        with open(self.cache_file, "w") as f:
            json.dump(cache_data, f, indent=2)
        os.chmod(self.cache_file, 0o600)  # rw------- (owner only)
        return token_data["access_token"]

    def get_token(self):
        token = self._get_cached_token()
        if token:
            return token
        return self._fetch_new_token()

    def cleanup_token_cache(self):
        """Securely remove token cache file"""
        if os.path.exists(self.cache_file):
            # Overwrite file with zeros before deletion for security
            with open(self.cache_file, "r+b") as f:
                length = f.seek(0, 2)  # Get file size
                f.seek(0)
                f.write(b"\0" * length)  # Overwrite with zeros
            os.remove(self.cache_file)


# OpenTelemetry Setup (matches weather app pattern)
# Traces
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter())
)

# Metrics
metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
metrics.set_meter_provider(MeterProvider(metric_readers=[metric_reader]))

# Logs (for events)
logs.set_logger_provider(LoggerProvider())
logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)


# Telemetry Callback Handler for Multi-Agent Workflow
class TelemetryCallback(BaseCallbackHandler):
    """Comprehensive callback handler for multi-agent workflow telemetry."""

    def __init__(self):
        super().__init__()
        self.llm_calls = []
        self.tool_calls = []
        self.current_llm_call = None
        self.current_tool = None
        self.current_chain = None

    def on_llm_start(self, serialized, prompts, **kwargs):
        """Capture LLM start event with request parameters."""
        invocation_params = kwargs.get("invocation_params", {})
        self.current_llm_call = {
            "prompts": prompts,
            "model": serialized.get("id", [None])[-1]
            if serialized.get("id")
            else "unknown",
            "invocation_params": invocation_params,
            "input_messages": [],
            "output": None,
            "finish_reason": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

        # Extract messages from prompts
        for prompt in prompts:
            self.current_llm_call["input_messages"].append(
                {"role": "user", "content": prompt}
            )

    def on_llm_end(self, response: LLMResult, **kwargs):
        """Capture LLM end event with response and token usage."""
        if not self.current_llm_call:
            return

        if response.generations and len(response.generations) > 0:
            generation = response.generations[0][0]
            self.current_llm_call["output"] = generation.text
            self.current_llm_call["finish_reason"] = (
                generation.generation_info.get("finish_reason", "stop")
                if generation.generation_info
                else "stop"
            )

        # Extract token usage from response
        if response.llm_output and "token_usage" in response.llm_output:
            token_usage = response.llm_output["token_usage"]
            self.current_llm_call["input_tokens"] = token_usage.get(
                "prompt_tokens", 0
            )
            self.current_llm_call["output_tokens"] = token_usage.get(
                "completion_tokens", 0
            )
            self.current_llm_call["total_tokens"] = token_usage.get(
                "total_tokens", 0
            )
        else:
            self.current_llm_call["input_tokens"] = 0
            self.current_llm_call["output_tokens"] = 0
            self.current_llm_call["total_tokens"] = 0

        # Extract model name and response ID
        if response.llm_output:
            if "model_name" in response.llm_output:
                self.current_llm_call["response_model"] = response.llm_output[
                    "model_name"
                ]
            if "system_fingerprint" in response.llm_output:
                self.current_llm_call["system_fingerprint"] = (
                    response.llm_output["system_fingerprint"]
                )

        if (
            generation.generation_info
            and "response_id" in generation.generation_info
        ):
            self.current_llm_call["response_id"] = generation.generation_info[
                "response_id"
            ]

        self.llm_calls.append(self.current_llm_call.copy())
        self.current_llm_call = None

    def on_tool_start(self, serialized, input_str, **kwargs):
        """Capture tool start event."""
        self.current_tool = {
            "name": serialized.get("name", "unknown"),
            "input": input_str,
            "output": None,
        }

    def on_tool_end(self, output, **kwargs):
        """Capture tool end event."""
        if self.current_tool:
            self.current_tool["output"] = output
            self.tool_calls.append(self.current_tool.copy())
            self.current_tool = None

    def on_chain_start(self, serialized, inputs, **kwargs):
        """Capture chain/graph start event."""
        if serialized is None:
            serialized = {}
        self.current_chain = {
            "name": serialized.get(
                "name",
                serialized.get("id", ["unknown"])[-1]
                if serialized.get("id")
                else "unknown",
            ),
            "inputs": inputs,
        }

    def on_chain_end(self, outputs, **kwargs):
        """Capture chain/graph end event."""
        if self.current_chain:
            self.current_chain["outputs"] = outputs
            self.current_chain = None


# Helper function to convert LangChain messages to telemetry format
def convert_messages_to_telemetry(messages):
    """Convert LangChain messages to telemetry InputMessage/OutputMessage format."""
    telemetry_messages = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            telemetry_messages.append(
                InputMessage(role="user", parts=[Text(content=msg.content)])
            )
        elif isinstance(msg, AIMessage):
            telemetry_messages.append(
                OutputMessage(
                    role="assistant",
                    parts=[Text(content=msg.content)],
                    finish_reason="stop",
                )
            )
        elif isinstance(msg, SystemMessage):
            telemetry_messages.append(
                InputMessage(role="system", parts=[Text(content=msg.content)])
            )
    return telemetry_messages


# Configure URL exclusions for Cisco endpoints

# Exclude Cisco URLs from HTTP instrumentation
excluded_urls = [
    os.getenv(
        "CISCO_TOKEN_URL", "https://id.cisco.com/oauth2/default/v1/token"
    ),
    os.getenv(
        "CISCO_BASE_URL",
        "https://chat-ai.cisco.com/openai/deployments/gpt-4o-mini",
    ),
]


def url_filter(url):
    """Filter function to exclude specific URLs from tracing"""
    return not any(excluded_url in str(url) for excluded_url in excluded_urls)


# Apply exclusions to HTTP instrumentors
try:
    RequestsInstrumentor().instrument(url_filter=url_filter)
except Exception as e:
    print(f"Warning: Could not configure URL exclusions: {e}")
    pass


# State definition for our multi-agent workflow
class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    research_query: str
    research_results: str
    memory_context: str
    final_response: str
    # Telemetry context (not serialized by LangGraph, used for tracking)
    telemetry_handler: Any  # TelemetryHandler instance
    telemetry_callback: Any  # TelemetryCallback instance


def init_weaviate_client():
    """Initialize Weaviate client and create schema if needed."""
    try:
        weaviate_url = os.getenv("WEAVIATE_URL")
        if not weaviate_url:
            weaviate_host = os.getenv(
                "WEAVIATE_HOST", "weaviate-rag.demo-app.svc.cluster.local"
            )
            weaviate_port = os.getenv("WEAVIATE_PORT", "8080")
            weaviate_url = f"http://{weaviate_host}:{weaviate_port}"

        # Use older client API compatible with weaviate-client 4.4.4
        client = weaviate.Client(url=weaviate_url, timeout_config=(5, 15))
        return client
    except Exception as e:
        print(f"Warning: Could not connect to Weaviate at {weaviate_url}: {e}")
        print("Please ensure Weaviate is running and accessible")
        return None


# Static historical data to populate Weaviate (simulating previous conversations)
HISTORICAL_CONVERSATIONS = [
    {
        "topic": "artificial intelligence",
        "content": "Previous discussion about AI ethics and responsible development. Key points: need for transparency, bias mitigation, and human oversight in AI systems.",
        "timestamp": "2024-01-15",
        "context": "ethics, transparency, bias",
    },
    {
        "topic": "artificial intelligence",
        "content": "Earlier conversation about AI in healthcare. Discussed diagnostic accuracy improvements, patient privacy concerns, and regulatory challenges.",
        "timestamp": "2024-02-20",
        "context": "healthcare, diagnostics, privacy",
    },
    {
        "topic": "climate change",
        "content": "Previous analysis of renewable energy adoption rates. Noted significant cost reductions in solar and wind, policy impacts, and grid integration challenges.",
        "timestamp": "2024-01-10",
        "context": "renewable energy, policy, grid",
    },
    {
        "topic": "climate change",
        "content": "Discussion about carbon capture technologies. Covered direct air capture, industrial applications, and economic viability concerns.",
        "timestamp": "2024-03-05",
        "context": "carbon capture, technology, economics",
    },
    {
        "topic": "technology trends",
        "content": "Previous conversation about quantum computing progress. Discussed IBM and Google advances, potential applications in cryptography and optimization.",
        "timestamp": "2024-02-01",
        "context": "quantum computing, cryptography, optimization",
    },
    {
        "topic": "technology trends",
        "content": "Earlier discussion on edge computing adoption. Covered IoT integration, latency improvements, and security considerations.",
        "timestamp": "2024-02-15",
        "context": "edge computing, IoT, security",
    },
    {
        "topic": "artificial intelligence",
        "content": "Previous analysis of generative AI impact on creative industries. Discussed content creation, copyright concerns, and job displacement fears.",
        "timestamp": "2024-03-10",
        "context": "generative AI, creativity, copyright",
    },
    {
        "topic": "cybersecurity",
        "content": "Earlier conversation about ransomware trends and defense strategies. Covered zero-trust architecture, incident response, and cyber insurance.",
        "timestamp": "2024-01-25",
        "context": "ransomware, zero-trust, incident response",
    },
    {
        "topic": "space exploration",
        "content": "Previous discussion on commercial space industry growth. Analyzed SpaceX, Blue Origin, and satellite internet initiatives.",
        "timestamp": "2024-02-10",
        "context": "commercial space, satellites, SpaceX",
    },
    {
        "topic": "biotechnology",
        "content": "Earlier analysis of CRISPR gene editing advances. Discussed therapeutic applications, ethical concerns, and regulatory frameworks.",
        "timestamp": "2024-01-20",
        "context": "CRISPR, gene editing, ethics",
    },
    {
        "topic": "climate change",
        "content": "Previous conversation about climate adaptation strategies. Covered infrastructure resilience, water management, and urban planning.",
        "timestamp": "2024-03-15",
        "context": "adaptation, infrastructure, urban planning",
    },
    {
        "topic": "artificial intelligence",
        "content": "Earlier discussion on AI regulation and governance. Analyzed EU AI Act, US policy approaches, and international cooperation challenges.",
        "timestamp": "2024-02-28",
        "context": "regulation, governance, policy",
    },
]


def setup_weaviate_schema_and_data(client):
    """Create schema and populate with historical conversation data only if it doesn't exist."""
    try:
        # Check if class already exists
        if client.schema.exists("Conversation"):
            # Check if data already exists
            result = (
                client.query.aggregate("Conversation").with_meta_count().do()
            )
            count = (
                result.get("data", {})
                .get("Aggregate", {})
                .get("Conversation", [{}])[0]
                .get("meta", {})
                .get("count", 0)
            )
            if count > 0:
                return True
            else:
                print("Schema exists but no data found - populating...")
        else:
            # Create class schema
            print("Creating Weaviate schema...")
            conversation_class = {
                "class": "Conversation",
                "properties": [
                    {"name": "topic", "dataType": ["text"]},
                    {"name": "content", "dataType": ["text"]},
                    {"name": "timestamp", "dataType": ["text"]},
                    {"name": "context", "dataType": ["text"]},
                ],
            }
            client.schema.create_class(conversation_class)

        # Populate with data
        print(
            f"Populating Weaviate with {len(HISTORICAL_CONVERSATIONS)} historical conversations..."
        )
        with client.batch as batch:
            for conv in HISTORICAL_CONVERSATIONS:
                batch.add_data_object(
                    data_object={
                        "topic": conv["topic"],
                        "content": conv["content"],
                        "timestamp": conv["timestamp"],
                        "context": conv["context"],
                    },
                    class_name="Conversation",
                )

        print(
            f"Successfully populated Weaviate with {len(HISTORICAL_CONVERSATIONS)} historical conversations"
        )
        return True

    except Exception as e:
        print(f"Error setting up Weaviate: {e}")
        return False


# Initialize Cisco Token Manager
cisco_client_id = os.getenv("CISCO_CLIENT_ID")
cisco_client_secret = os.getenv("CISCO_CLIENT_SECRET")
cisco_app_key = os.getenv("CISCO_APP_KEY")

if not all([cisco_client_id, cisco_client_secret, cisco_app_key]):
    token_manager = None
else:
    token_manager = TokenManager(
        cisco_client_id, cisco_client_secret, cisco_app_key
    )

# Initialize Weaviate
weaviate_client = init_weaviate_client()
if weaviate_client:
    setup_weaviate_schema_and_data(weaviate_client)


# Helper function to create Cisco LLM instances
def create_cisco_llm(callbacks=None):
    """Create a standardized Cisco LLM instance with fresh token and optional callbacks."""
    if not token_manager:
        return None

    try:
        access_token = token_manager.get_token()
        return ChatOpenAI(
            temperature=0.7,  # Increased from 0.1 for more variation
            api_key="dummy-key",
            base_url=os.getenv(
                "CISCO_BASE_URL",
                "https://chat-ai.cisco.com/openai/deployments/gpt-4o-mini",
            ),
            model="gpt-4o-mini",
            default_headers={"api-key": access_token},
            model_kwargs={"user": f'{{"appkey": "{cisco_app_key}"}}'},
            callbacks=callbacks if callbacks else [],
        )
    except Exception as e:
        print(f"Error creating Cisco LLM: {e}")
        return None


# LLM instances will be created dynamically when needed


@tool
def tavily_search(query: str) -> str:
    """Search the web for current information using Tavily."""
    try:
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            return "Error: TAVILY_API_KEY environment variable not set"

        tavily = TavilySearch(api_key=tavily_api_key, max_results=3)
        return tavily.run(query)
    except Exception as e:
        return f"Error performing search: {str(e)}"


@tool
def query_memory(topic: str) -> str:
    """Query historical conversations and context from Weaviate vector database."""
    if not weaviate_client:
        relevant_conversations = [
            conv
            for conv in HISTORICAL_CONVERSATIONS
            if topic.lower() in conv["topic"].lower()
        ]
        if relevant_conversations:
            context = "\n".join(
                [
                    f"• {conv['content']} (Context: {conv['context']})"
                    for conv in relevant_conversations[:2]
                ]
            )
            return f"📚 Historical Context from Memory:\n{context}"
        return "📚 No relevant historical context found in memory."

    try:
        response = (
            weaviate_client.query.get(
                "Conversation", ["topic", "content", "context", "timestamp"]
            )
            .with_near_text({"concepts": [topic]})
            .with_limit(2)
            .do()
        )

        if response.get("data", {}).get("Get", {}).get("Conversation"):
            conversations = response["data"]["Get"]["Conversation"]
            context = "\n".join(
                [
                    f"• {conv['content']} (Context: {conv['context']})"
                    for conv in conversations
                ]
            )
            return f"📚 Historical Context from Memory:\n{context}"
        else:
            return (
                "📚 No relevant historical context found in memory database."
            )

    except Exception as e:
        # Fallback to static search if Weaviate query fails
        print(f"Weaviate query failed, using static fallback: {e}")
        relevant_conversations = [
            conv
            for conv in HISTORICAL_CONVERSATIONS
            if any(
                word in conv["topic"].lower()
                or word in conv["content"].lower()
                for word in topic.lower().split()
            )
        ]
        if relevant_conversations:
            context = "\n".join(
                [
                    f"• {conv['content']} (Context: {conv['context']})"
                    for conv in relevant_conversations[:2]
                ]
            )
            return f"📚 Historical Context from Memory (Fallback):\n{context}"
        return "📚 No relevant historical context found in memory."


def get_autonomous_research_agent():
    """Create autonomous research agent with fresh LLM instance."""
    research_llm = create_cisco_llm()
    if not research_llm:
        return None
    return create_react_agent(model=research_llm, tools=[tavily_search])


def research_agent(state: AgentState):
    """Research agent that autonomously decides when and how to use search tools."""
    print("🔬 Research Agent activated")

    # Get telemetry context from state
    handler = state.get("telemetry_handler")
    callback = state.get("telemetry_callback")

    last_message = state["messages"][-1]
    query = (
        last_message.content
        if hasattr(last_message, "content")
        else str(last_message)
    )

    # Create Agent span
    agent = Agent(
        name="research_agent",
        operation="invoke",
        agent_type="research",
        framework="langgraph",
        model="gpt-4o-mini",
        tools=["tavily_search"],
        description="Autonomous research agent using web search",
        input_context=query,
    )

    if handler:
        handler.start_agent(agent)

    # Create Task span
    task = Task(
        name="research_task",
        task_type="research",
        objective="Search and analyze current information",
        source="agent",
        input_data=query,
    )

    if handler:
        handler.start_task(task)

    try:
        # Clear callback data for this agent
        if callback:
            callback.llm_calls.clear()
            callback.tool_calls.clear()

        autonomous_research_agent = get_autonomous_research_agent()
        if not autonomous_research_agent:
            raise Exception("Could not create research agent")

        agent_input = {
            "messages": [
                HumanMessage(content=f"Research and analyze: {query}")
            ]
        }
        result = autonomous_research_agent.invoke(
            agent_input, config={"callbacks": [callback] if callback else []}
        )
        final_message = result["messages"][-1]
        research_results = (
            f"🔍 **Autonomous Research Analysis:**\n{final_message.content}"
        )

        # Track LLM invocations from callback
        if handler and callback and callback.llm_calls:
            for llm_call_data in callback.llm_calls:
                llm_invocation = LLMInvocation(
                    request_model="gpt-4o-mini",
                    response_model_name=llm_call_data.get(
                        "response_model", "gpt-4o-mini"
                    ),
                    provider="cisco_ai",
                    framework="langgraph",
                    operation="chat",
                    input_messages=[
                        InputMessage(role="user", parts=[Text(content=query)])
                    ],
                    output_messages=[
                        OutputMessage(
                            role="assistant",
                            parts=[
                                Text(content=llm_call_data.get("output", ""))
                            ],
                            finish_reason=llm_call_data.get(
                                "finish_reason", "stop"
                            ),
                        )
                    ],
                    input_tokens=llm_call_data.get("input_tokens", 0),
                    output_tokens=llm_call_data.get("output_tokens", 0),
                )
                handler.start_llm(llm_invocation)
                handler.stop_llm(llm_invocation)

    except Exception as e:
        # Fallback to manual tool calling if autonomous agent fails
        print(
            f"Autonomous agent failed, falling back to manual tool calling: {e}"
        )
        raw_search_results = tavily_search(query)
        research_results = (
            f"🔍 **Research Results (Fallback):**\n{raw_search_results}"
        )

    # Stop Task and Agent spans
    if handler:
        task.output_result = research_results
        handler.stop_task(task)

        agent.output_result = research_results
        handler.stop_agent(agent)

    return {
        "research_query": query,
        "research_results": research_results,
        "messages": [
            AIMessage(content=f"Autonomous research completed for: {query}")
        ],
    }


def get_memory_llm():
    """Create memory LLM with fresh token and tools."""
    llm = create_cisco_llm()
    if not llm:
        return None
    return llm.bind_tools([query_memory])


def memory_agent(state: AgentState):
    """Memory agent using manual tool calling approach."""
    print("🧠 Memory Agent activated")

    # Get telemetry context from state
    handler = state.get("telemetry_handler")
    callback = state.get("telemetry_callback")

    query = state.get("research_query", "")

    # Create Agent span
    agent = Agent(
        name="memory_agent",
        operation="invoke",
        agent_type="memory",
        framework="langgraph",
        model="gpt-4o-mini",
        tools=["query_memory"],
        description="Memory agent for historical context retrieval",
        input_context=query,
    )

    if handler:
        handler.start_agent(agent)

    # Create Task span
    task = Task(
        name="memory_retrieval_task",
        task_type="retrieval",
        objective="Retrieve and analyze historical context",
        source="agent",
        input_data=query,
    )

    if handler:
        handler.start_task(task)

    decision_prompt = f"""
You are a memory analyst. For the query: "{query}"

You should ALMOST ALWAYS search historical conversations unless the query is extremely specific and technical.

For topics like AI, ethics, technology, business, science, etc. - ALWAYS search for historical context.

Decide:
- "SEARCH: <search_terms>" - Extract 2-3 key terms from the query to search for
- "SKIP: <reason>" - Only if this is a very specific technical question with no historical relevance

Default to SEARCH unless absolutely certain no historical context exists.
"""

    try:
        # Clear callback data for this agent
        if callback:
            callback.llm_calls.clear()
            callback.tool_calls.clear()

        memory_llm = get_memory_llm()
        if not memory_llm:
            raise Exception("Could not create memory LLM")

        decision_response = memory_llm.invoke(
            [HumanMessage(content=decision_prompt)],
            config={"callbacks": [callback] if callback else []},
        )
        decision = decision_response.content.strip()

        # Track decision LLM call
        if handler and callback and callback.llm_calls:
            for llm_call_data in callback.llm_calls:
                llm_invocation = LLMInvocation(
                    request_model="gpt-4o-mini",
                    response_model_name=llm_call_data.get(
                        "response_model", "gpt-4o-mini"
                    ),
                    provider="cisco_ai",
                    framework="langgraph",
                    operation="chat",
                    input_messages=[
                        InputMessage(
                            role="user", parts=[Text(content=decision_prompt)]
                        )
                    ],
                    output_messages=[
                        OutputMessage(
                            role="assistant",
                            parts=[Text(content=decision)],
                            finish_reason="stop",
                        )
                    ],
                    input_tokens=llm_call_data.get("input_tokens", 0),
                    output_tokens=llm_call_data.get("output_tokens", 0),
                )
                handler.start_llm(llm_invocation)
                handler.stop_llm(llm_invocation)
            callback.llm_calls.clear()

        if decision.startswith("SEARCH:"):
            search_terms = decision.replace("SEARCH:", "").strip()
            print(f"🔍 Memory agent decided to search for: {search_terms}")
            raw_memory_context = query_memory.invoke({"topic": search_terms})
            analysis_prompt = f"""
Analyze this historical context for the query "{query}":

{raw_memory_context}

Provide:
1. Key insights from historical discussions
2. How this relates to the current query
3. Important patterns or evolution
4. Lessons learned
"""

            analysis_llm = create_cisco_llm(
                callbacks=[callback] if callback else None
            )
            if not analysis_llm:
                raise Exception("Could not create analysis LLM")

            analysis_response = analysis_llm.invoke(
                [HumanMessage(content=analysis_prompt)]
            )
            memory_context = (
                f"🧠 **Manual Memory Analysis:**\n{analysis_response.content}"
            )

            # Track analysis LLM call
            if handler and callback and callback.llm_calls:
                for llm_call_data in callback.llm_calls:
                    llm_invocation = LLMInvocation(
                        request_model="gpt-4o-mini",
                        response_model_name=llm_call_data.get(
                            "response_model", "gpt-4o-mini"
                        ),
                        provider="cisco_ai",
                        framework="langgraph",
                        operation="chat",
                        input_messages=[
                            InputMessage(
                                role="user",
                                parts=[Text(content=analysis_prompt)],
                            )
                        ],
                        output_messages=[
                            OutputMessage(
                                role="assistant",
                                parts=[
                                    Text(content=analysis_response.content)
                                ],
                                finish_reason="stop",
                            )
                        ],
                        input_tokens=llm_call_data.get("input_tokens", 0),
                        output_tokens=llm_call_data.get("output_tokens", 0),
                    )
                    handler.start_llm(llm_invocation)
                    handler.stop_llm(llm_invocation)

        else:
            reason = decision.replace("SKIP:", "").strip()
            print(f"🚫 Memory agent decided to skip search: {reason}")
            memory_context = f"🧠 **Memory Decision:** No historical search needed. {reason}"

    except Exception as e:
        print(f"Manual memory agent failed, using simple query: {e}")
        raw_memory_context = query_memory.invoke({"topic": query})
        memory_context = (
            f"🧠 **Memory Context (Fallback):**\n{raw_memory_context}"
        )

    # Stop Task and Agent spans
    if handler:
        task.output_result = memory_context
        handler.stop_task(task)

        agent.output_result = memory_context
        handler.stop_agent(agent)

    return {
        "memory_context": memory_context,
        "messages": [AIMessage(content="Manual memory analysis completed")],
    }


def synthesizer_agent(state: AgentState):
    """Synthesizer agent that uses LLM to intelligently combine research and memory."""
    print("🎯 Synthesizer Agent activated")

    # Get telemetry context from state
    handler = state.get("telemetry_handler")
    callback = state.get("telemetry_callback")

    research = state.get("research_results", "")
    memory = state.get("memory_context", "")
    query = state.get("research_query", "")

    # Create Agent span
    agent = Agent(
        name="synthesizer_agent",
        operation="invoke",
        agent_type="synthesizer",
        framework="langgraph",
        model="gpt-4o-mini",
        description="Synthesizer agent for combining research and memory",
        input_context=f"Research: {research[:100]}... Memory: {memory[:100]}...",
    )

    if handler:
        handler.start_agent(agent)

    # Create Task span
    task = Task(
        name="synthesis_task",
        task_type="synthesis",
        objective="Synthesize research and memory into comprehensive response",
        source="agent",
        input_data=query,
    )

    if handler:
        handler.start_task(task)

    synthesis_prompt = f"""
You are an expert analyst tasked with creating a comprehensive response by synthesizing current research with historical context.

Original Query: "{query}"

Current Research:
{research}

Historical Context:
{memory}

Please create a comprehensive analysis that:
1. Addresses the original query directly
2. Integrates current findings with historical insights
3. Identifies key trends, changes, or continuities
4. Provides actionable insights or conclusions
5. Highlights what's new vs. what's consistent over time

Structure your response with clear sections and make it informative and engaging.
"""

    try:
        # Clear callback data for this agent
        if callback:
            callback.llm_calls.clear()
            callback.tool_calls.clear()

        # Create fresh LLM for synthesis
        synthesizer_llm = create_cisco_llm(
            callbacks=[callback] if callback else None
        )
        if not synthesizer_llm:
            raise Exception("Could not create LLM for synthesis")

        synthesis_response = synthesizer_llm.invoke(
            [HumanMessage(content=synthesis_prompt)]
        )
        final_response = f"🎯 **Comprehensive Analysis for: {query}**\n\n{synthesis_response.content}"

        # Track synthesis LLM call
        if handler and callback and callback.llm_calls:
            for llm_call_data in callback.llm_calls:
                llm_invocation = LLMInvocation(
                    request_model="gpt-4o-mini",
                    response_model_name=llm_call_data.get(
                        "response_model", "gpt-4o-mini"
                    ),
                    provider="cisco_ai",
                    framework="langgraph",
                    operation="chat",
                    input_messages=[
                        InputMessage(
                            role="user", parts=[Text(content=synthesis_prompt)]
                        )
                    ],
                    output_messages=[
                        OutputMessage(
                            role="assistant",
                            parts=[Text(content=synthesis_response.content)],
                            finish_reason="stop",
                        )
                    ],
                    input_tokens=llm_call_data.get("input_tokens", 0),
                    output_tokens=llm_call_data.get("output_tokens", 0),
                )
                handler.start_llm(llm_invocation)
                handler.stop_llm(llm_invocation)

    except Exception as e:
        final_response = f"🎯 **Error:** Could not create synthesis: {str(e)}"

    # Stop Task and Agent spans
    if handler:
        task.output_result = final_response
        handler.stop_task(task)

        agent.output_result = final_response
        handler.stop_agent(agent)

    return {
        "final_response": final_response,
        "messages": [AIMessage(content="Comprehensive analysis completed")],
    }


def create_multi_agent_workflow():
    workflow = StateGraph(AgentState)

    workflow.add_node("research", research_agent)
    workflow.add_node("memory", memory_agent)
    workflow.add_node("synthesizer", synthesizer_agent)

    workflow.set_entry_point("research")
    workflow.add_edge("research", "memory")
    workflow.add_edge("memory", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile()


# Initialize Flask app
app_flask = Flask(__name__)
CORS(app_flask)

# Global variable to store the workflow
workflow_app = None


def initialize_workflow():
    """Initialize the multi-agent workflow"""
    global workflow_app
    workflow_app = create_multi_agent_workflow()
    print("🚀 Multi-Agent RAG Workflow initialized")


@app_flask.route("/", methods=["GET"])
def home():
    """Health check endpoint"""
    return jsonify(
        {
            "service": "LangGraph Multi-Agent RAG",
            "status": "healthy",
            "version": "1.0.0",
            "description": "Multi-agent system with Research, Memory, and Synthesizer agents",
            "endpoints": {"health": "/health", "query": "/query (POST)"},
        }
    )


@app_flask.route("/health", methods=["GET"])
def health():
    """Detailed health check"""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "LangGraph Multi-Agent RAG",
            "version": "1.0.0",
            "workflow_initialized": workflow_app is not None,
        }
    )


@app_flask.route("/query", methods=["POST"])
def process_query():
    """Process query through multi-agent workflow with comprehensive telemetry"""
    try:
        if not workflow_app:
            return jsonify(
                {
                    "error": "Workflow not initialized",
                    "message": "Service is starting up, please try again in a moment",
                }
            ), 503

        data = request.get_json()
        if not data or "query" not in data:
            return jsonify(
                {
                    "error": "Invalid request",
                    "message": "Request must contain 'query' field",
                }
            ), 400

        query = data["query"]
        session_id = str(uuid.uuid4())

        print(f"\n🎯 Processing query: {query[:100]}...")
        print(f"📋 Session ID: {session_id}")

        # Initialize telemetry
        handler = get_telemetry_handler()
        telemetry_callback = TelemetryCallback()

        # Start workflow
        workflow = Workflow(
            name="multi_agent_rag_workflow",
            workflow_type="sequential",
            description="Multi-agent RAG with research, memory, and synthesis",
            framework="langgraph",
            initial_input=query,
        )
        handler.start_workflow(workflow)

        start_time = time.time()

        # Create initial state WITH telemetry context
        initial_state = AgentState(
            messages=[HumanMessage(content=query)],
            research_query="",
            research_results="",
            memory_context="",
            final_response="",
            telemetry_handler=handler,  # Pass handler to agents
            telemetry_callback=telemetry_callback,  # Pass callback to agents
        )

        # Run the workflow (LangGraph will call our agents internally with telemetry context)
        result = workflow_app.invoke(initial_state)

        end_time = time.time()
        processing_time = end_time - start_time

        # Set workflow final output
        workflow.final_output = result.get("final_response", "")
        workflow.attributes["workflow.processing_time"] = processing_time
        workflow.attributes["workflow.session_id"] = session_id
        handler.stop_workflow(workflow)

        print(f"✅ Query processed in {processing_time:.2f} seconds")

        return jsonify(
            {
                "session_id": session_id,
                "query": query,
                "response": result.get("final_response", ""),
                "research_results": result.get("research_results", ""),
                "memory_context": result.get("memory_context", ""),
                "processing_time_seconds": round(processing_time, 2),
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        print(f"❌ Error processing query: {e}")
        if "workflow" in locals():
            workflow.final_output = f"Error: {str(e)}"
            handler.stop_workflow(workflow)
        return jsonify({"error": "Processing failed", "message": str(e)}), 500


def run_flask_app():
    """Run Flask application"""
    print("🌐 Starting Flask web service...")
    print("🔗 Available endpoints:")
    print("  - GET  /        : Service information")
    print("  - GET  /health  : Health check")
    print("  - POST /query   : Submit query for analysis")
    print("📡 Server listening on http://0.0.0.0:8000")

    app_flask.run(host="0.0.0.0", port=8000, debug=False, threaded=True)


if __name__ == "__main__":
    # Initialize workflow in background
    print("🔧 Initializing Multi-Agent RAG Web Service...")
    initialize_workflow()

    # Start Flask app
    run_flask_app()
