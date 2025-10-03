import asyncio
import base64
import json
import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import LLMResult
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Import GenAI telemetry utilities
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    AgentInvocation as Agent,
)
from opentelemetry.util.genai.types import (
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
    ToolCallResponse,
    Workflow,
)
from opentelemetry.util.genai.types import ToolCall as TelemetryToolCall

load_dotenv()
os.environ.setdefault(
    "OTEL_SERVICE_NAME",
    os.getenv("OTEL_SERVICE_NAME", "langgraph-mcp-weather-single-agent"),
)

# Exclude Cisco AI endpoints from instrumentation
os.environ.setdefault(
    "OTEL_PYTHON_REQUESTS_EXCLUDED_URLS",
    "https://chat-ai.cisco.com,https://id.cisco.com/oauth2/default/v1/token",
)

# Set environment variables for GenAI content capture
os.environ.setdefault(
    "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
)
os.environ.setdefault(
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true"
)
os.environ.setdefault(
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT_MODE", "SPAN_AND_EVENT"
)
os.environ.setdefault(
    "OTEL_INSTRUMENTATION_GENAI_EMITTERS", "span_metric_event"
)

# Configure OpenTelemetry with OTLP exporters
# Traces
trace.set_tracer_provider(TracerProvider())
span_processor = BatchSpanProcessor(OTLPSpanExporter())
trace.get_tracer_provider().add_span_processor(span_processor)

# Metrics
metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
metrics.set_meter_provider(MeterProvider(metric_readers=[metric_reader]))

# Logs (for events)
logs.set_logger_provider(LoggerProvider())
logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)


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


class TelemetryCallback(BaseCallbackHandler):
    """Callback to capture LangChain/LangGraph execution details for GenAI telemetry."""

    def __init__(self):
        self.llm_calls = []
        self.tool_calls = []
        self.chain_calls = []
        self.agent_actions = []
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
            "temperature": invocation_params.get("temperature"),
            "max_tokens": invocation_params.get("max_tokens"),
            "top_p": invocation_params.get("top_p"),
            "frequency_penalty": invocation_params.get("frequency_penalty"),
            "presence_penalty": invocation_params.get("presence_penalty"),
            "request_id": kwargs.get("run_id"),
            "parent_run_id": kwargs.get("parent_run_id"),
            "tags": kwargs.get("tags", []),
        }

    def on_llm_end(self, response: LLMResult, **kwargs):
        """Capture LLM end event with token usage and response details."""
        if self.current_llm_call:
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
                    self.current_llm_call["response_model"] = (
                        response.llm_output["model_name"]
                    )
                if "system_fingerprint" in response.llm_output:
                    self.current_llm_call["system_fingerprint"] = (
                        response.llm_output["system_fingerprint"]
                    )

            if (
                generation.generation_info
                and "response_id" in generation.generation_info
            ):
                self.current_llm_call["response_id"] = (
                    generation.generation_info["response_id"]
                )

            self.llm_calls.append(self.current_llm_call.copy())
            self.current_llm_call = None

    def on_chain_start(self, serialized, inputs, **kwargs):
        """Capture chain/graph start event."""
        if serialized is None:
            serialized = {}

        chain_name = serialized.get(
            "name", kwargs.get("name", "unknown_chain")
        )
        chain_type = (
            serialized.get("id", ["unknown"])[-1]
            if serialized.get("id")
            else "unknown"
        )

        chain_data = {
            "name": chain_name,
            "type": chain_type,
            "inputs": inputs,
            "run_id": kwargs.get("run_id"),
            "parent_run_id": kwargs.get("parent_run_id"),
            "tags": kwargs.get("tags", []),
            "metadata": kwargs.get("metadata", {}),
        }
        self.chain_calls.append(chain_data)
        self.current_chain = chain_data

    def on_chain_end(self, outputs, **kwargs):
        """Capture chain/graph end event."""
        if self.current_chain:
            self.current_chain["outputs"] = outputs
            self.current_chain = None

    def on_tool_start(self, serialized, input_str, **kwargs):
        """Capture tool start event."""
        tool_name = serialized.get("name", "unknown_tool")
        self.current_tool = {
            "name": tool_name,
            "input": input_str,
            "run_id": kwargs.get("run_id"),
            "parent_run_id": kwargs.get("parent_run_id"),
            "tags": kwargs.get("tags", []),
        }

    def on_tool_end(self, output, **kwargs):
        """Capture tool end event."""
        if self.current_tool:
            self.current_tool["output"] = output
            self.tool_calls.append(self.current_tool.copy())
            self.current_tool = None

    def on_agent_action(self, action, **kwargs):
        """Capture agent action."""
        self.agent_actions.append(
            {
                "type": "action",
                "tool": action.tool,
                "tool_input": action.tool_input,
                "log": action.log,
                "run_id": kwargs.get("run_id"),
            }
        )

    def on_agent_finish(self, finish, **kwargs):
        """Capture agent finish event."""
        self.agent_actions.append(
            {
                "type": "finish",
                "output": finish.return_values,
                "log": finish.log,
                "run_id": kwargs.get("run_id"),
            }
        )


# Initialize Cisco token manager
cisco_client_id = os.getenv("CISCO_CLIENT_ID")
cisco_client_secret = os.getenv("CISCO_CLIENT_SECRET")
cisco_app_key = os.getenv("CISCO_APP_KEY")

if not all([cisco_client_id, cisco_client_secret, cisco_app_key]):
    token_manager = None
    model = None
else:
    token_manager = TokenManager(
        cisco_client_id, cisco_client_secret, cisco_app_key
    )

    # Initialize the model with Cisco AI service
    try:
        access_token = token_manager.get_token()
        model = ChatOpenAI(
            temperature=0.1,
            api_key="dummy-key",
            base_url="https://chat-ai.cisco.com/openai/deployments/gpt-4o-mini",
            model="gpt-4o-mini",
            default_headers={"api-key": access_token},
            model_kwargs={"user": f'{{"appkey": "{cisco_app_key}"}}'},
        )
    except Exception:
        model = None


# Initialize Flask app
app = Flask(__name__)
CORS(app)


@tool
async def get_weather(city: str) -> str:
    """Get weather for a given city using MCP server."""
    server_params = StdioServerParameters(
        command="python", args=["mcp_weather.py"], env=None
    )
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_weather", {"location": city}
                )
                if result.content:
                    content = result.content[0]
                    if hasattr(content, "text"):
                        data = json.loads(content.text)

                        if data.get("status") == "success":
                            weather = data["current_weather"]
                            return f"Weather in {city}: {weather['temperature']}, Wind: {weather['wind_speed']}"
                        else:
                            return f"Error getting weather for {city}: {data.get('error', 'Unknown error')}"
                    else:
                        return f"Weather data received for {city}: {content}"
                else:
                    return f"No weather data received for {city}"

    except Exception as e:
        return f"Failed to get weather for {city}: {str(e)}"


# Create agent instance with telemetry callback (only if model is available)
agent = None
telemetry_callback = TelemetryCallback()

if model:
    agent = create_react_agent(
        model=model,
        tools=[get_weather],
        prompt="You are a helpful weather assistant powered by Cisco AI. Use the weather tool to provide accurate, current weather information for any city requested. After providing the weather data, always add a brief one-line personal commentary about the weather conditions (e.g., whether it's pleasant, extreme, unusual, etc.). Be expressive and opinionated in your commentary.",
    )


@app.route("/", methods=["GET"])
def home():
    """Home endpoint with API information."""
    return jsonify(
        {
            "message": "LangGraph MCP Weather Agent API - Powered by Cisco AI",
            "version": "1.0.0",
            "ai_service": "Cisco AI (gpt-4o-mini)",
            "status": "ready"
            if agent
            else "unavailable - missing Cisco credentials",
            "endpoints": {
                "/": "GET - API information",
                "/weather": "POST - Get weather for a city",
                "/health": "GET - Health check",
            },
            "usage": {
                "weather_endpoint": {
                    "method": "POST",
                    "body": {"city": "San Francisco"},
                    "example": "curl -X POST http://localhost:5000/weather -H 'Content-Type: application/json' -d '{\"city\": \"San Francisco\"}'",
                }
            },
            "required_env_vars": [
                "CISCO_CLIENT_ID",
                "CISCO_CLIENT_SECRET",
                "CISCO_APP_KEY",
            ],
        }
    )


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify(
        {
            "status": "healthy" if agent else "degraded",
            "service": "mcp-weather-agent",
            "ai_service": "Cisco AI" if agent else "unavailable",
            "token_manager": "active" if token_manager else "inactive",
        }
    )


@app.route("/weather", methods=["POST"])
def get_weather_endpoint():
    """Get weather for a specified city."""
    if not agent:
        return jsonify(
            {
                "error": "Service unavailable - Cisco AI model not initialized",
                "details": "Please check Cisco credentials in environment variables",
                "status": "error",
            }
        ), 503

    try:
        data = request.get_json()
        if not data or "city" not in data:
            return jsonify(
                {
                    "error": "Missing 'city' parameter in request body",
                    "example": {"city": "San Francisco"},
                }
            ), 400

        city = data["city"]
        if not city or not isinstance(city, str):
            return jsonify({"error": "City must be a non-empty string"}), 400

        # Refresh token if needed before processing
        if token_manager:
            try:
                fresh_token = token_manager.get_token()
                model.default_headers["api-key"] = fresh_token
            except Exception as e:
                return jsonify(
                    {
                        "error": f"Failed to refresh Cisco token: {str(e)}",
                        "status": "error",
                    }
                ), 503

        # Run the agent asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(process_weather_request(city))
            return jsonify(
                {
                    "city": city,
                    "response": result,
                    "status": "success",
                    "powered_by": "Cisco AI",
                }
            )
        finally:
            loop.close()

    except Exception as e:
        return jsonify(
            {
                "error": f"Failed to process weather request: {str(e)}",
                "status": "error",
            }
        ), 500


def convert_langchain_messages_to_telemetry(messages):
    """Convert LangChain messages to telemetry format."""
    telemetry_messages = []

    for msg in messages:
        if isinstance(msg, HumanMessage):
            telemetry_messages.append(
                InputMessage(role="user", parts=[Text(content=msg.content)])
            )
        elif isinstance(msg, AIMessage):
            parts = []
            if msg.content:
                parts.append(Text(content=msg.content))
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    parts.append(
                        TelemetryToolCall(
                            id=tc["id"],
                            name=tc["name"],
                            arguments=tc["args"],
                        )
                    )
            if parts:
                telemetry_messages.append(
                    InputMessage(role="assistant", parts=parts)
                )
        elif isinstance(msg, ToolMessage):
            telemetry_messages.append(
                InputMessage(
                    role="tool",
                    parts=[
                        ToolCallResponse(
                            id=msg.tool_call_id,
                            response=msg.content,
                        )
                    ],
                )
            )

    return telemetry_messages


async def process_weather_request(city: str) -> str:
    """Process weather request using the LangGraph agent with telemetry."""
    handler = get_telemetry_handler()
    telemetry_callback.llm_calls.clear()
    telemetry_callback.tool_calls.clear()
    telemetry_callback.chain_calls.clear()

    # Start workflow
    workflow = Workflow(
        name="weather_query_workflow",
        workflow_type="react_agent",
        description="Weather query using MCP tool",
        framework="langgraph",
        initial_input=f"What is the weather in {city}?",
    )
    handler.start_workflow(workflow)

    # Create agent (represents agent creation/initialization)
    agent_create = Agent(
        name="weather_agent",
        operation="create",
        agent_type="react",
        framework="langgraph",
        model="gpt-4o-mini",
        tools=["get_weather"],
        description="Weather assistant using MCP tool",
        system_instructions="You are a helpful weather assistant powered by Cisco AI. Use the weather tool to provide accurate, current weather information for any city requested. After providing the weather data, always add a brief one-line personal commentary about the weather conditions (e.g., whether it's pleasant, extreme, unusual, etc.). Be expressive and opinionated in your commentary.",
    )
    handler.start_agent(agent_create)
    handler.stop_agent(agent_create)

    # Invoke agent (represents agent execution)
    agent_obj = Agent(
        name="weather_agent",
        operation="invoke",
        agent_type="react",
        framework="langgraph",
        model="gpt-4o-mini",
        input_context=f"What is the weather in {city}?",
    )
    handler.start_agent(agent_obj)

    try:
        messages = []
        all_messages = []
        llm_call_index = 0

        # Add the initial user message to all_messages
        user_message = HumanMessage(content=f"What is the weather in {city}?")
        all_messages.append(user_message)

        async for chunk in agent.astream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"What is the weather in {city}?",
                    }
                ]
            },
            config={"callbacks": [telemetry_callback]},
        ):
            for node_name, node_update in chunk.items():
                if "messages" in node_update:
                    for message in node_update["messages"]:
                        # Skip if it's a duplicate of the user message we already added
                        if (
                            isinstance(message, HumanMessage)
                            and message.content == user_message.content
                        ):
                            continue
                        all_messages.append(message)
                        if hasattr(message, "content") and message.content:
                            messages.append(message.content)

                        # Create LLM invocation telemetry for AI messages
                        if isinstance(
                            message, AIMessage
                        ) and llm_call_index < len(
                            telemetry_callback.llm_calls
                        ):
                            llm_call_data = telemetry_callback.llm_calls[
                                llm_call_index
                            ]
                            llm_call_index += 1

                            # Convert messages to telemetry format
                            input_msgs = (
                                convert_langchain_messages_to_telemetry(
                                    all_messages[:-1]
                                )
                            )

                            # Create output message
                            output_parts = []
                            if message.content:
                                output_parts.append(
                                    Text(content=message.content)
                                )

                            if (
                                hasattr(message, "tool_calls")
                                and message.tool_calls
                            ):
                                for tc in message.tool_calls:
                                    output_parts.append(
                                        TelemetryToolCall(
                                            id=tc["id"],
                                            name=tc["name"],
                                            arguments=tc["args"],
                                        )
                                    )

                            output_msg = OutputMessage(
                                role="assistant",
                                parts=output_parts,
                                finish_reason=llm_call_data.get(
                                    "finish_reason", "stop"
                                ),
                            )

                            if (
                                hasattr(message, "tool_calls")
                                and message.tool_calls
                            ):
                                operation = "execute_tool"
                            else:
                                operation = "chat"

                            # Create LLM invocation
                            actual_model = llm_call_data.get(
                                "response_model",
                                llm_call_data.get("model", "gpt-4o-mini"),
                            )
                            llm_invocation = LLMInvocation(
                                request_model="gpt-4o-mini",
                                response_model_name=actual_model,
                                provider="cisco_ai",
                                framework="langgraph",
                                operation=operation,
                                input_messages=input_msgs,
                                output_messages=[output_msg],
                                agent_name="weather_agent",
                                agent_id=str(agent_obj.run_id),
                            )

                            # Populate token usage
                            llm_invocation.input_tokens = llm_call_data.get(
                                "input_tokens", 0
                            )
                            llm_invocation.output_tokens = llm_call_data.get(
                                "output_tokens", 0
                            )

                            if llm_call_data.get("response_id"):
                                llm_invocation.response_id = llm_call_data[
                                    "response_id"
                                ]
                            if llm_call_data.get("request_id"):
                                llm_invocation.run_id = llm_call_data[
                                    "request_id"
                                ]
                            if llm_call_data.get("parent_run_id"):
                                llm_invocation.parent_run_id = llm_call_data[
                                    "parent_run_id"
                                ]

                            # Populate attributes
                            if llm_call_data.get("temperature") is not None:
                                llm_invocation.attributes[
                                    "gen_ai.request.temperature"
                                ] = llm_call_data["temperature"]
                            if llm_call_data.get("max_tokens") is not None:
                                llm_invocation.attributes[
                                    "gen_ai.request.max_tokens"
                                ] = llm_call_data["max_tokens"]
                            if llm_call_data.get("top_p") is not None:
                                llm_invocation.attributes[
                                    "gen_ai.request.top_p"
                                ] = llm_call_data["top_p"]

                            llm_invocation.attributes[
                                "gen_ai.response.finish_reasons"
                            ] = [llm_call_data.get("finish_reason", "stop")]

                            handler.start_llm(llm_invocation)
                            handler.stop_llm(llm_invocation)

        final_response = (
            messages[-1]
            if messages
            else f"Unable to get weather information for {city}"
        )

        # Complete agent and workflow
        agent_obj.output_result = final_response
        handler.stop_agent(agent_obj)

        workflow.final_output = final_response
        workflow.attributes["workflow.llm_calls"] = len(
            telemetry_callback.llm_calls
        )
        workflow.attributes["workflow.tool_calls"] = len(
            telemetry_callback.tool_calls
        )
        handler.stop_workflow(workflow)

        return final_response

    except Exception as e:
        agent_obj.output_result = f"Error: {str(e)}"
        handler.stop_agent(agent_obj)
        workflow.final_output = f"Error: {str(e)}"
        handler.stop_workflow(workflow)
        return f"Error processing weather request for {city}: {str(e)}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
