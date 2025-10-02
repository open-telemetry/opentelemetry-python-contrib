#!/usr/bin/env python3
"""
Example demonstrating OpenTelemetry GenAI telemetry for agentic AI use cases.

This example shows:
1. Workflow orchestration with multiple agents
2. Agent creation and invocation
3. Task execution
4. LLM calls within agent context
5. Parent-child span relationships
6. Metrics and events emission
"""

import time

from opentelemetry import _logs as logs
from opentelemetry import metrics, trace
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    ConsoleLogExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.util.genai.handler import get_telemetry_handler
from opentelemetry.util.genai.types import (
    Agent,
    Error,
    InputMessage,
    LLMInvocation,
    OutputMessage,
    Task,
    Text,
    ToolCall,
    ToolCallResponse,
    Workflow,
)


def setup_telemetry():
    # Set up tracing
    trace_provider = TracerProvider()
    trace_provider.add_span_processor(
        SimpleSpanProcessor(ConsoleSpanExporter())
    )
    trace.set_tracer_provider(trace_provider)

    # Set up metrics
    metric_reader = PeriodicExportingMetricReader(
        ConsoleMetricExporter(), export_interval_millis=5000
    )
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Set up logging (for events)
    logger_provider = LoggerProvider()
    logger_provider.add_log_record_processor(
        SimpleLogRecordProcessor(ConsoleLogExporter())
    )
    logs.set_logger_provider(logger_provider)

    return trace_provider, meter_provider, logger_provider


def simulate_multi_agent_workflow():
    """
    Simulate a multi-agent customer support workflow.

    Workflow: customer_support_pipeline
      ├─ Agent: create_agent (classifier_agent)
      ├─ Agent: invoke_agent (classifier_agent)
      │   └─ Task: classify_intent
      │       └─ LLM: chat (with agent context)
      ├─ Agent: create_agent (support_agent)
      └─ Agent: invoke_agent (support_agent)
          └─ Task: handle_request
              └─ LLM: chat (with agent context)
    """

    handler = get_telemetry_handler()

    # 1. Start Workflow
    print("Starting workflow: customer_support_pipeline")
    workflow = Workflow(
        name="customer_support_pipeline",
        workflow_type="sequential",
        description="Multi-agent customer support workflow",
        framework="custom",
        initial_input="User query: My order hasn't arrived yet",
    )
    handler.start_workflow(workflow)
    time.sleep(0.1)  # Simulate work

    # 2. Create Classifier Agent
    print("Creating agent: classifier_agent")
    classifier_agent = Agent(
        name="classifier_agent",
        operation="create",
        agent_type="classifier",
        description="Classifies customer intents",
        framework="custom",
        model="gpt-4",
        tools=["intent_classifier"],
        system_instructions="You are a customer intent classifier. Categorize queries into: order_status, refund, technical_support, or general.",
    )
    handler.start_agent(classifier_agent)
    time.sleep(0.05)
    handler.stop_agent(classifier_agent)

    # 3. Invoke Classifier Agent
    print("Invoking agent: classifier_agent")
    classifier_invocation = Agent(
        name="classifier_agent",
        operation="invoke",
        agent_type="classifier",
        framework="custom",
        model="gpt-4",
        input_context="User query: My order hasn't arrived yet",
        run_id=classifier_agent.run_id,  # Link to created agent
    )
    handler.start_agent(classifier_invocation)
    time.sleep(0.1)

    # 4. Task: Classify Intent
    print("Executing task: classify_intent")
    classify_task = Task(
        name="classify_intent",
        task_type="classification",
        objective="Determine the user's intent from their query",
        source="agent",
        status="in_progress",
        input_data="My order hasn't arrived yet",
    )
    handler.start_task(classify_task)
    time.sleep(0.05)

    # 5. LLM Call within Task (with agent context)
    print("LLM call with agent context")
    llm_invocation = LLMInvocation(
        request_model="gpt-4",
        provider="openai",
        framework="custom",
        input_messages=[
            InputMessage(
                role="system",
                parts=[Text(content="You are a customer intent classifier.")],
            ),
            InputMessage(
                role="user",
                parts=[Text(content="My order hasn't arrived yet")],
            ),
        ],
        # Agent context - links this LLM call to the agent
        agent_name="classifier_agent",
        agent_id=str(classifier_agent.run_id),
    )
    handler.start_llm(llm_invocation)
    time.sleep(0.1)

    # Simulate LLM response
    llm_invocation.output_messages = [
        OutputMessage(
            role="assistant",
            parts=[Text(content="Intent: order_status")],
            finish_reason="stop",
        )
    ]
    llm_invocation.input_tokens = 45
    llm_invocation.output_tokens = 8
    handler.stop_llm(llm_invocation)

    # Complete task
    classify_task.output_data = "order_status"
    classify_task.status = "completed"
    handler.stop_task(classify_task)

    # Complete agent invocation
    classifier_invocation.output_result = "Intent classified as: order_status"
    handler.stop_agent(classifier_invocation)

    # 6. Create Support Agent
    print("Creating agent: support_agent")
    support_agent = Agent(
        name="support_agent",
        operation="create",
        agent_type="support",
        description="Handles customer support requests",
        framework="custom",
        model="gpt-4",
        tools=["order_lookup", "shipping_tracker"],
        system_instructions="You are a helpful customer support agent. Assist with order status inquiries.",
    )
    handler.start_agent(support_agent)
    time.sleep(0.05)
    handler.stop_agent(support_agent)

    # 7. Invoke Support Agent
    print("Invoking agent: support_agent")
    support_invocation = Agent(
        name="support_agent",
        operation="invoke",
        agent_type="support",
        framework="custom",
        model="gpt-4",
        input_context="Handle order_status query: My order hasn't arrived yet",
        run_id=support_agent.run_id,
    )
    handler.start_agent(support_invocation)
    time.sleep(0.1)

    # 8. Task: Handle Request
    print("  📝 Executing task: handle_request")
    handle_task = Task(
        name="handle_request",
        task_type="execution",
        objective="Provide order status information to customer",
        source="agent",
        assigned_agent="support_agent",
        status="in_progress",
        input_data="Query about order status",
    )
    handler.start_task(handle_task)
    time.sleep(0.05)

    # 9. LLM Call for Support Response
    print("LLM call with agent context")
    support_llm = LLMInvocation(
        request_model="gpt-4",
        provider="openai",
        framework="custom",
        input_messages=[
            InputMessage(
                role="system",
                parts=[
                    Text(
                        content="You are a helpful customer support agent. Assist with order status inquiries."
                    )
                ],
            ),
            InputMessage(
                role="user",
                parts=[Text(content="My order hasn't arrived yet")],
            ),
            # Include the classifier agent's output in the conversation history
            InputMessage(
                role="assistant",
                parts=[Text(content="Intent: order_status")],
            ),
            # Simulate a tool call made by the assistant to check order status
            InputMessage(
                role="assistant",
                parts=[
                    ToolCall(
                        id="call_abc123",
                        name="check_order_status",
                        arguments={"order_id": "ORD-12345"},
                    )
                ],
            ),
            # Tool response with the order status information
            InputMessage(
                role="tool",
                parts=[
                    ToolCallResponse(
                        id="call_abc123",
                        response="Order ORD-12345 is in transit. Expected delivery: 2-3 business days.",
                    )
                ],
            ),
        ],
        # Agent context
        agent_name="support_agent",
        agent_id=str(support_agent.run_id),
    )
    handler.start_llm(support_llm)
    time.sleep(0.1)

    support_llm.output_messages = [
        OutputMessage(
            role="assistant",
            parts=[
                Text(
                    content="I've checked your order status. Your package is currently in transit and should arrive within 2-3 business days."
                )
            ],
            finish_reason="stop",
        )
    ]
    support_llm.input_tokens = 52
    support_llm.output_tokens = 28
    handler.stop_llm(support_llm)

    # Complete task
    handle_task.output_data = "Order status provided to customer"
    handle_task.status = "completed"
    handler.stop_task(handle_task)

    # Complete agent invocation
    support_invocation.output_result = "Customer informed about order status"
    handler.stop_agent(support_invocation)

    # 10. Complete Workflow
    print("Completing workflow")
    workflow.final_output = "Customer query resolved: Order status provided"
    handler.stop_workflow(workflow)

    print("\n" + "=" * 80)
    print("Workflow completed! Check the console output above for:")
    print("  • Span hierarchy (Workflow → Agent → Task → LLM)")
    print(
        "  • Agent context on LLM spans (gen_ai.agent.name, gen_ai.agent.id)"
    )
    print("  • Metrics with agent attributes")
    print("  • Events for workflow/agent/task (if content capture enabled)")
    print("=" * 80 + "\n")


def simulate_error_handling():
    """Demonstrate error handling in agentic workflows."""
    print("\n" + "=" * 80)
    print("ERROR HANDLING EXAMPLE")
    print("=" * 80 + "\n")

    handler = get_telemetry_handler()

    # Start a workflow that will fail
    workflow = Workflow(
        name="failing_workflow",
        workflow_type="sequential",
        description="Demonstrates error handling",
        framework="custom",
        initial_input="Test error handling",
    )
    handler.start_workflow(workflow)

    # Agent that encounters an error
    agent = Agent(
        name="error_agent",
        operation="invoke",
        agent_type="test",
        framework="custom",
    )
    handler.start_agent(agent)

    # Simulate an error
    error = Error(
        message="Simulated agent failure",
        type=RuntimeError,
    )
    handler.fail_agent(agent, error)
    handler.fail_workflow(workflow, error)

    print("Error handling demonstrated - check spans for error status\n")


if __name__ == "__main__":
    # Set up telemetry
    trace_provider, meter_provider, logger_provider = setup_telemetry()

    # Run examples
    simulate_multi_agent_workflow()

    # Wait a bit for metrics to be exported
    time.sleep(1)

    simulate_error_handling()

    # Wait for final metric export
    time.sleep(6)
