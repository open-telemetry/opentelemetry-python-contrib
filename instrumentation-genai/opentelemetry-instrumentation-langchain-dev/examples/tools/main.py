import logging

from flask import Flask, jsonify, request
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

# todo: start a server span here
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
from opentelemetry.instrumentation.flask import FlaskInstrumentor
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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up instrumentation
LangChainInstrumentor().instrument()


@tool
def add(a: int, b: int) -> int:
    """Add two integers.

    Args:
        a: First integer
        b: Second integer
    """
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers.

    Args:
        a: First integer
        b: Second integer
    """
    return a * b


# -----------------------------------------------------------------------------
# Flask app
# -----------------------------------------------------------------------------
app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)


@app.post("/tools_add_multiply")
def tools():
    """POST form-url-encoded or JSON with message (and optional session_id)."""
    payload = request.get_json(silent=True) or request.form  # allow either
    query = payload.get("message")
    if not query:
        logger.error("Missing 'message' field in request")
        return jsonify({"error": "Missing 'message' field."}), 400

    try:
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
        tools = [add, multiply]
        llm_with_tools = llm.bind_tools(tools)

        messages = [HumanMessage(query)]
        ai_msg = llm_with_tools.invoke(messages)
        print("LLM output:\n", ai_msg)
        messages.append(ai_msg)

        for tool_call in ai_msg.tool_calls:
            selected_tool = {"add": add, "multiply": multiply}[
                tool_call["name"].lower()
            ]
            if selected_tool is not None:
                tool_msg = selected_tool.invoke(tool_call)
                messages.append(tool_msg)
        print("messages:\n", messages)

        result = llm_with_tools.invoke(messages)
        print("LLM output:\n", result)
        logger.info(f"LLM response: {result.content}")

        return result.content
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    # When run directly: python app.py
    app.run(host="0.0.0.0", port=5001)
