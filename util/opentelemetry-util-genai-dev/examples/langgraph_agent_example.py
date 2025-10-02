#!/usr/bin/env python3
"""
LangGraph ReAct Agent Example with Manual OpenTelemetry Instrumentation.

This example demonstrates:
1. A LangGraph ReAct agent that answers capital city questions
2. Full manual instrumentation using opentelemetry-util-genai-dev
3. Workflow for graph execution, Agent for ReAct agent, Tasks for each step
4. Manual LLM invocation tracking (not using OpenAI instrumentation)
5. Tool usage tracking with proper telemetry

The agent uses create_react_agent to build a simple ReAct agent that can
look up capital cities.

Requirements:
- langgraph
- langchain-openai
- opentelemetry-util-genai-dev

Run with:
  export OPENAI_API_KEY=your_key_here
  python examples/langgraph_agent_example.py
"""

import os
import random
import time

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import LLMResult
from langchain_core.tools import tool
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
    Task,
    Text,
    ToolCallResponse,
    Workflow,
)
from opentelemetry.util.genai.types import (
    ToolCall as TelemetryToolCall,
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
    """Comprehensive callback to capture all LangChain/LangGraph execution details.

    Captures data from:
    - LLM calls (on_llm_start/end) - for LLMInvocation spans
    - Chain/Graph execution (on_chain_start/end) - for Workflow tracking
    - Tool calls (on_tool_start/end) - for Task/Tool tracking
    - Agent actions (on_agent_action/finish) - for Agent tracking
    """

    def __init__(self):
        self.llm_calls = []
        self.chain_calls = []
        self.tool_calls = []
        self.agent_actions = []
        self.current_llm_call = None
        self.current_chain = None
        self.current_tool = None

    def on_llm_start(self, serialized, prompts, **kwargs):
        """Capture LLM start event with all request parameters."""
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
        """Capture chain/graph start event for Workflow tracking."""
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
        """Capture tool start event for Task/Tool tracking."""
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


# Define the tool
@tool
def get_capital(country: str) -> str:
    """Get the capital city of a country.

    Args:
        country: The name of the country

    Returns:
        The capital city of the country
    """
    capitals = {
        "france": "Paris",
        "germany": "Berlin",
        "italy": "Rome",
        "spain": "Madrid",
        "japan": "Tokyo",
        "china": "Beijing",
        "india": "New Delhi",
        "brazil": "Brasília",
        "canada": "Ottawa",
        "australia": "Canberra",
    }
    result = capitals.get(country.lower(), f"Unknown capital for {country}")
    print(f"Tool called: get_capital({country}) -> {result}")
    return result


def convert_langchain_messages_to_telemetry(messages):
    """Convert LangChain messages to our telemetry format."""
    telemetry_messages = []

    for msg in messages:
        if isinstance(msg, HumanMessage):
            telemetry_messages.append(
                InputMessage(role="user", parts=[Text(content=msg.content)])
            )
        elif isinstance(msg, AIMessage):
            parts = []
            # Add text content
            if msg.content:
                parts.append(Text(content=msg.content))
            # Add tool calls
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


def run_agent_with_telemetry(question: str):
    """Run the ReAct agent with full telemetry instrumentation."""

    handler = get_telemetry_handler()
    telemetry_callback = TelemetryCallback()

    # 1. Start Workflow
    print(f"\n{'='*80}")
    print(f"QUESTION: {question}")
    print(f"{'='*80}\n")

    workflow = Workflow(
        name="capital_question_workflow",
        workflow_type="react_agent",
        description="LangGraph ReAct agent answering capital city questions",
        framework="langgraph",
        initial_input=question,
    )
    handler.start_workflow(workflow)

    # 2. Create Agent with all attributes populated
    print(f"\n{'='*80}")
    print("Creating ReAct agent...")
    print(f"{'='*80}\n")
    agent_obj = Agent(
        name="capital_agent",
        operation="create",
        agent_type="react",
        description="ReAct agent that can look up capital cities",
        framework="langgraph",
        model="gpt-4",
        tools=["get_capital"],
        system_instructions="You are a helpful assistant that answers questions about capital cities. Use the get_capital tool when needed.",
    )
    # Populate additional agent attributes
    agent_obj.attributes["agent.version"] = "1.0"
    agent_obj.attributes["agent.temperature"] = 0
    handler.start_agent(agent_obj)

    # Create the LangGraph agent with callback
    llm = ChatOpenAI(
        model="gpt-4", temperature=0, callbacks=[telemetry_callback]
    )
    tools = [get_capital]
    graph = create_react_agent(llm, tools)

    handler.stop_agent(agent_obj)

    # 3. Invoke Agent
    print(f"\n{'='*80}")
    print("Invoking agent...")
    print(f"{'='*80}\n")
    agent_invocation = Agent(
        name="capital_agent",
        operation="invoke",
        agent_type="react",
        framework="langgraph",
        model="gpt-4",
        input_context=question,
        run_id=agent_obj.run_id,
    )
    handler.start_agent(agent_invocation)

    # Run the graph with callbacks to capture real data
    messages = [HumanMessage(content=question)]
    step_count = 0
    llm_call_index = 0  # Track which LLM call we're processing

    for event in graph.stream(
        {"messages": messages},
        config={"callbacks": [telemetry_callback]},
        stream_mode="values",
    ):
        step_count += 1
        current_messages = event["messages"]
        last_message = current_messages[-1]

        print(f"\n--- Step {step_count} ---")
        print(f"Message type: {type(last_message).__name__}")

        # Create task for this step
        if isinstance(last_message, AIMessage):
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                # Agent decided to use a tool
                task_name = "tool_planning"
                task_type = "planning"
                objective = f"Decide to call tool: {last_message.tool_calls[0]['name']}"
            else:
                # Agent provided final answer
                task_name = "final_response"
                task_type = "generation"
                objective = "Generate final response to user"
        elif isinstance(last_message, ToolMessage):
            task_name = "tool_execution"
            task_type = "execution"
            objective = "Execute tool and return result"
        else:
            task_name = f"step_{step_count}"
            task_type = "processing"
            objective = "Process message"

        task = Task(
            name=task_name,
            task_type=task_type,
            objective=objective,
            source="agent",
            assigned_agent="capital_agent",
            status="in_progress",
            input_data=str(last_message.content)[:100]
            if hasattr(last_message, "content")
            else "",
        )
        handler.start_task(task)

        # If this is an AI message, create LLM invocation telemetry from captured data
        if isinstance(last_message, AIMessage):
            print(
                f"AI Response: {last_message.content[:100] if last_message.content else '(tool call)'}..."
            )
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                print(
                    f"Tool calls: {[tc['name'] for tc in last_message.tool_calls]}"
                )

            # Get LLM call data from callback if available
            if llm_call_index < len(telemetry_callback.llm_calls):
                llm_call_data = telemetry_callback.llm_calls[llm_call_index]
                llm_call_index += 1

                # Convert messages to telemetry format
                input_msgs = convert_langchain_messages_to_telemetry(
                    current_messages[:-1]
                )

                # Create output message with tool calls if present
                output_parts = []
                if last_message.content:
                    output_parts.append(Text(content=last_message.content))

                # Add tool calls to output parts
                if (
                    hasattr(last_message, "tool_calls")
                    and last_message.tool_calls
                ):
                    for tc in last_message.tool_calls:
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
                    finish_reason=llm_call_data.get("finish_reason", "stop"),
                )

                # Get actual model name from response
                actual_model = llm_call_data.get(
                    "response_model", llm_call_data.get("model", "gpt-4")
                )

                if (
                    hasattr(last_message, "tool_calls")
                    and last_message.tool_calls
                ):
                    operation = "execute_tool"
                else:
                    operation = "chat"

                # Create LLM invocation with real data from callbacks
                llm_invocation = LLMInvocation(
                    request_model="gpt-4",
                    response_model_name=actual_model,
                    provider="openai",
                    framework="langgraph",
                    operation=operation,
                    input_messages=input_msgs,
                    output_messages=[output_msg],
                    agent_name="capital_agent",
                    agent_id=str(agent_obj.run_id),
                )

                # Populate all token-related attributes from real data
                llm_invocation.input_tokens = llm_call_data.get(
                    "input_tokens", 0
                )
                llm_invocation.output_tokens = llm_call_data.get(
                    "output_tokens", 0
                )

                # Populate response_id if available
                if llm_call_data.get("response_id"):
                    llm_invocation.response_id = llm_call_data["response_id"]

                # Populate run_id and parent_run_id from LangChain
                if llm_call_data.get("request_id"):
                    llm_invocation.run_id = llm_call_data["request_id"]
                if llm_call_data.get("parent_run_id"):
                    llm_invocation.parent_run_id = llm_call_data[
                        "parent_run_id"
                    ]

                # Populate attributes dict with gen_ai.* semantic convention attributes
                if llm_call_data.get("temperature") is not None:
                    llm_invocation.attributes["gen_ai.request.temperature"] = (
                        llm_call_data["temperature"]
                    )
                if llm_call_data.get("max_tokens") is not None:
                    llm_invocation.attributes["gen_ai.request.max_tokens"] = (
                        llm_call_data["max_tokens"]
                    )
                if llm_call_data.get("top_p") is not None:
                    llm_invocation.attributes["gen_ai.request.top_p"] = (
                        llm_call_data["top_p"]
                    )
                if llm_call_data.get("frequency_penalty") is not None:
                    llm_invocation.attributes[
                        "gen_ai.request.frequency_penalty"
                    ] = llm_call_data["frequency_penalty"]
                if llm_call_data.get("presence_penalty") is not None:
                    llm_invocation.attributes[
                        "gen_ai.request.presence_penalty"
                    ] = llm_call_data["presence_penalty"]
                if llm_call_data.get("system_fingerprint"):
                    llm_invocation.attributes[
                        "gen_ai.response.system_fingerprint"
                    ] = llm_call_data["system_fingerprint"]

                # Add finish reasons as an attribute
                llm_invocation.attributes["gen_ai.response.finish_reasons"] = [
                    llm_call_data.get("finish_reason", "stop")
                ]

                print(
                    f"Token Usage: Input={llm_invocation.input_tokens}, Output={llm_invocation.output_tokens}"
                )
                print(
                    f"Model: {actual_model}, Finish Reason: {llm_call_data.get('finish_reason', 'stop')}"
                )

                handler.start_llm(llm_invocation)
                handler.stop_llm(llm_invocation)

        elif isinstance(last_message, ToolMessage):
            print(f"Tool result: {last_message.content}")

        # Complete task
        task.output_data = (
            str(last_message.content)[:100]
            if hasattr(last_message, "content")
            else "completed"
        )
        task.status = "completed"
        handler.stop_task(task)

    # Get final answer
    final_message = current_messages[-1]
    final_answer = (
        final_message.content
        if isinstance(final_message, AIMessage)
        else str(final_message)
    )

    # Complete agent invocation
    agent_invocation.output_result = final_answer
    handler.stop_agent(agent_invocation)

    # Complete workflow
    workflow.final_output = final_answer
    # Populate workflow attributes from captured data
    workflow.attributes["workflow.steps"] = step_count
    workflow.attributes["workflow.llm_calls"] = len(
        telemetry_callback.llm_calls
    )
    workflow.attributes["workflow.tool_calls"] = len(
        telemetry_callback.tool_calls
    )
    handler.stop_workflow(workflow)

    # Log captured telemetry summary
    print(f"\n{'='*80}")
    print("Telemetry Summary:")
    print(f"  LLM calls captured: {len(telemetry_callback.llm_calls)}")
    print(f"  Tool calls captured: {len(telemetry_callback.tool_calls)}")
    for tool_call in telemetry_callback.tool_calls:
        print(
            f"    - {tool_call['name']}: {tool_call['input']} -> {tool_call['output']}"
        )
    print(f"  Chain/Graph executions: {len(telemetry_callback.chain_calls)}")
    if telemetry_callback.agent_actions:
        print(f"  Agent actions: {len(telemetry_callback.agent_actions)}")
    print(f"{'='*80}\n")

    print(f"\n{'='*80}")
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
    ]

    # Pick a random question
    question = random.choice(questions)

    # Run the agent
    run_agent_with_telemetry(question)

    # Wait for metrics to export
    print(f"\n{'='*80}")
    print("Waiting for metrics export...")
    print(f"{'='*80}\n")
    time.sleep(6)


if __name__ == "__main__":
    main()
