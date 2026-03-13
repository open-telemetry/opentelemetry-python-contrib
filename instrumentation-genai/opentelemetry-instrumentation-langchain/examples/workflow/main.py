"""
LangGraph StateGraph example with an LLM node.

Similar to the manual example (../manual/main.py) but uses LangGraph's StateGraph
with a node that calls ChatOpenAI. OpenTelemetry LangChain instrumentation traces
the LLM calls made from within the graph node.
"""

import base64
from typing import Annotated
import os
import json
from datetime import datetime, timedelta

import requests


from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from opentelemetry import _logs, metrics, trace
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
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


# Configure tracing
trace.set_tracer_provider(TracerProvider())
span_processor = BatchSpanProcessor(OTLPSpanExporter())
trace.get_tracer_provider().add_span_processor(span_processor)

# Configure logging
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)

# Configure metrics
metrics.set_meter_provider(
    MeterProvider(
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(),
            ),
        ]
    )
)


class GraphState(TypedDict):
    """State for the graph; messages are accumulated with add_messages."""

    messages: Annotated[list, add_messages]


def build_graph(llm: ChatOpenAI):
    """Build a StateGraph with a single LLM node."""

    def llm_node(state: GraphState) -> dict:
        """Node that invokes the LLM with the current messages."""
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(GraphState)
    builder.add_node("llm", llm_node)
    builder.add_edge(START, "llm")
    builder.add_edge("llm", END)
    return builder.compile()


def main():
    # Set up instrumentation (traces LLM calls from within graph nodes)
    LangChainInstrumentor().instrument()

    # ChatOpenAI setup
    user_md = {"appkey": cisco_app_key} if cisco_app_key else {}
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.1,
        max_tokens=100,
        top_p=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.5,
        stop_sequences=["\n", "Human:", "AI:"],
        seed=100,
    )

    graph = build_graph(llm)

    initial_messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = graph.invoke({"messages": initial_messages})

    print("LangGraph output (messages):")
    for msg in result.get("messages", []):
        print(f"  {type(msg).__name__}: {msg.content}")

    # Un-instrument after use
    LangChainInstrumentor().uninstrument()


if __name__ == "__main__":
    main()
