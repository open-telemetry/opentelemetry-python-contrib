#!/usr/bin/env python3
"""
Simple LangGraph Agent Example with Manual OpenTelemetry Instrumentation.

This example demonstrates:
1. A simple LangGraph agent (no tools) that answers capital city questions
2. Manual instrumentation using opentelemetry-util-genai-dev
3. Agent telemetry without Workflow or Task (just Agent + LLM)
4. The LLM answers directly from its knowledge (no tool calls)

This is the simplest possible example showing how to instrument a LangGraph
agent that just wraps an LLM call.

Requirements:
- langgraph
- langchain-openai
- opentelemetry-util-genai-dev

Run with:
  export OPENAI_API_KEY=your_key_here
  python examples/langgraph_simple_agent_example.py
"""

import os
import random
import time

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

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
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    Agent,
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Text,
)

# Set environment variables for content capture
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


class TelemetryCallback(BaseCallbackHandler):
    """Custom callback to capture LangChain/LangGraph execution details.

    Captures data from:
    - LLM calls (on_llm_start/end)
    - Chain/Graph execution (on_chain_start/end)
    - Agent actions (on_agent_action/finish)
    """

    def __init__(self):
        self.llm_calls = []
        self.chain_calls = []
        self.agent_actions = []
        self.current_llm_call = None
        self.current_chain = None

    def on_llm_start(self, serialized, prompts, **kwargs):
        """Capture LLM start event."""
        invocation_params = kwargs.get("invocation_params", {})
        self.current_llm_call = {
            "prompts": prompts,
            "model": serialized.get("id", [None])[-1]
            if serialized.get("id")
            else "unknown",
            "invocation_params": invocation_params,
            # Capture request parameters for gen_ai.* attributes
            "temperature": invocation_params.get("temperature"),
            "max_tokens": invocation_params.get("max_tokens"),
            "top_p": invocation_params.get("top_p"),
            "top_k": invocation_params.get("top_k"),
            "frequency_penalty": invocation_params.get("frequency_penalty"),
            "presence_penalty": invocation_params.get("presence_penalty"),
            "stop_sequences": invocation_params.get("stop"),
            "request_id": kwargs.get("run_id"),  # LangChain run_id
            "parent_run_id": kwargs.get("parent_run_id"),
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
                # Fallback if token usage not available
                self.current_llm_call["input_tokens"] = 0
                self.current_llm_call["output_tokens"] = 0
                self.current_llm_call["total_tokens"] = 0

            # Extract model name and response ID from response
            if response.llm_output:
                if "model_name" in response.llm_output:
                    self.current_llm_call["response_model"] = (
                        response.llm_output["model_name"]
                    )
                if "system_fingerprint" in response.llm_output:
                    self.current_llm_call["system_fingerprint"] = (
                        response.llm_output["system_fingerprint"]
                    )

            # Extract response ID from generation info
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
        # LangGraph sometimes passes serialized=None
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

        self.current_chain = {
            "name": chain_name,
            "type": chain_type,
            "inputs": inputs,
            "run_id": kwargs.get("run_id"),
            "parent_run_id": kwargs.get("parent_run_id"),
            "tags": kwargs.get("tags", []),
            "metadata": kwargs.get("metadata", {}),
        }

    def on_chain_end(self, outputs, **kwargs):
        """Capture chain/graph end event."""
        if self.current_chain:
            self.current_chain["outputs"] = outputs
            self.chain_calls.append(self.current_chain.copy())
            self.current_chain = None

    def on_agent_action(self, action, **kwargs):
        """Capture agent action (tool call decision)."""
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


def run_simple_agent_with_telemetry(question: str):
    """Run a simple agent with telemetry (Agent + LLM only, no Workflow/Task)."""

    handler = get_telemetry_handler()
    telemetry_callback = TelemetryCallback()

    print(f"\n{'='*80}")
    print(f"QUESTION: {question}")
    print(f"{'='*80}\n")

    # 1. Create Agent with all attributes populated
    print(f"\n{'='*80}")
    print("create_agent span...")
    print(f"{'='*80}\n")
    agent_obj = Agent(
        name="simple_capital_agent",
        operation="create",
        agent_type="qa",
        description="Simple agent that answers capital city questions from knowledge",
        framework="langgraph",
        model="gpt-4",
        system_instructions="You are a helpful assistant that answers questions about capital cities using your knowledge.",
    )
    # Populate additional attributes for the agent
    agent_obj.attributes["agent.version"] = "1.0"
    agent_obj.attributes["agent.temperature"] = 0  # From LLM config
    handler.start_agent(agent_obj)

    # Create the LangGraph agent (no tools) with callback
    llm = ChatOpenAI(
        model="gpt-4", temperature=0, callbacks=[telemetry_callback]
    )
    graph = create_react_agent(llm, tools=[])  # Empty tools list

    handler.stop_agent(agent_obj)

    # 2. Invoke Agent
    print(f"\n{'='*80}")
    print("invoke_agent span")
    print(f"{'='*80}\n")
    agent_invocation = Agent(
        name="simple_capital_agent",
        operation="invoke",
        agent_type="qa",
        framework="langgraph",
        model="gpt-4",
        input_context=question,
        run_id=agent_obj.run_id,
    )
    handler.start_agent(agent_invocation)

    # Run the graph with callbacks to capture real data
    messages = [HumanMessage(content=question)]
    result = graph.invoke(
        {"messages": messages}, config={"callbacks": [telemetry_callback]}
    )

    # Extract the response
    final_message = result["messages"][-1]
    final_answer = final_message.content

    print(f"{'='*80}")
    print(f"AI Response: {final_answer}\n")
    print(f"{'='*80}")

    # 3. Create LLM Invocation telemetry from captured callback data
    if telemetry_callback.llm_calls:
        llm_call_data = telemetry_callback.llm_calls[
            0
        ]  # Get the first (and likely only) LLM call

        # Create user message from the question
        user_msg = InputMessage(role="user", parts=[Text(content=question)])

        # Output message from actual LLM response
        output_msg = OutputMessage(
            role="assistant",
            parts=[Text(content=final_answer)],
            finish_reason=llm_call_data.get("finish_reason", "stop"),
        )

        # Get actual model name from response or use request model
        actual_model = llm_call_data.get(
            "response_model", llm_call_data.get("model", "gpt-4")
        )

        # Create LLM invocation with real data from callbacks
        llm_invocation = LLMInvocation(
            request_model="gpt-4",
            response_model_name=actual_model,  # Use response_model_name field
            provider="openai",
            framework="langgraph",
            input_messages=[user_msg],
            output_messages=[output_msg],
            agent_name="simple_capital_agent",
            agent_id=str(agent_obj.run_id),
        )

        # Populate all token-related attributes
        llm_invocation.input_tokens = llm_call_data.get("input_tokens", 0)
        llm_invocation.output_tokens = llm_call_data.get("output_tokens", 0)

        # Populate response_id if available
        if llm_call_data.get("response_id"):
            llm_invocation.response_id = llm_call_data["response_id"]

        # Populate run_id and parent_run_id from LangChain
        if llm_call_data.get("request_id"):
            llm_invocation.run_id = llm_call_data["request_id"]
        if llm_call_data.get("parent_run_id"):
            llm_invocation.parent_run_id = llm_call_data["parent_run_id"]

        # Populate attributes dict with gen_ai.* semantic convention attributes
        # These will be emitted as span attributes by the emitters
        if llm_call_data.get("temperature") is not None:
            llm_invocation.attributes["gen_ai.request.temperature"] = (
                llm_call_data["temperature"]
            )
        if llm_call_data.get("max_tokens") is not None:
            llm_invocation.attributes["gen_ai.request.max_tokens"] = (
                llm_call_data["max_tokens"]
            )
        if llm_call_data.get("top_p") is not None:
            llm_invocation.attributes["gen_ai.request.top_p"] = llm_call_data[
                "top_p"
            ]
        if llm_call_data.get("top_k") is not None:
            llm_invocation.attributes["gen_ai.request.top_k"] = llm_call_data[
                "top_k"
            ]
        if llm_call_data.get("frequency_penalty") is not None:
            llm_invocation.attributes["gen_ai.request.frequency_penalty"] = (
                llm_call_data["frequency_penalty"]
            )
        if llm_call_data.get("presence_penalty") is not None:
            llm_invocation.attributes["gen_ai.request.presence_penalty"] = (
                llm_call_data["presence_penalty"]
            )
        if llm_call_data.get("stop_sequences") is not None:
            llm_invocation.attributes["gen_ai.request.stop_sequences"] = (
                llm_call_data["stop_sequences"]
            )
        if llm_call_data.get("system_fingerprint"):
            llm_invocation.attributes["gen_ai.response.system_fingerprint"] = (
                llm_call_data["system_fingerprint"]
            )

        # Add finish reasons as an attribute (semantic convention)
        llm_invocation.attributes["gen_ai.response.finish_reasons"] = [
            llm_call_data.get("finish_reason", "stop")
        ]

        print(f"{'='*80}")
        print(
            f"Token Usage (from LangChain): Input={llm_invocation.input_tokens}, Output={llm_invocation.output_tokens}"
        )
        print(
            f"Model: {actual_model}, Finish Reason: {llm_call_data.get('finish_reason', 'stop')}\n"
        )
        print(f"{'='*80}")

        handler.start_llm(llm_invocation)
        handler.stop_llm(llm_invocation)
    else:
        print(f"\n{'=' * 80}")
        print("No LLM calls captured by callback\n")
        print(f"{'=' * 80}\n")

    # Log chain/graph execution info if captured
    if telemetry_callback.chain_calls:
        print(f"{'=' * 80}")
        print(
            f"Captured {len(telemetry_callback.chain_calls)} chain/graph executions"
        )
        for chain in telemetry_callback.chain_calls:
            print(f"   - Chain: {chain['name']} (type: {chain['type']})")
        print(f"{'=' * 80}\n")

    # Log agent actions if captured
    if telemetry_callback.agent_actions:
        print(f"{'=' * 80}")
        print(
            f"Captured {len(telemetry_callback.agent_actions)} agent actions"
        )
        for action in telemetry_callback.agent_actions:
            if action["type"] == "action":
                print(f"   - Tool call: {action['tool']}")
            else:
                print("   - Agent finished")
        print(f"\n{'=' * 80}")

    # Complete agent invocation
    agent_invocation.output_result = final_answer
    handler.stop_agent(agent_invocation)

    print(f"{'='*80}")
    print(f"FINAL ANSWER: {final_answer}")
    print(f"{'='*80}\n")

    return final_answer


def main():
    """Main function to run the example."""
    # Telemetry is configured at module level (see above)

    # Sample questions
    questions = [
        "What is the capital of France?",
        "What is the capital of Japan?",
        "What is the capital of Brazil?",
        "What is the capital of Australia?",
        "What is the capital of Canada?",
    ]

    # Pick a random question
    question = random.choice(questions)

    # Run the agent
    run_simple_agent_with_telemetry(question)

    # Wait for metrics to export
    print(f"\n{'=' * 80}")
    print("\nWaiting for metrics export...")
    print(f"{'=' * 80}\n")
    time.sleep(6)


if __name__ == "__main__":
    main()
