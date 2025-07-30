from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

# from opentelemetry import trace
# from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
# from opentelemetry.sdk.trace import TracerProvider
# from opentelemetry.sdk.trace.export import BatchSpanProcessor
# # Configure tracing
# trace.set_tracer_provider(TracerProvider())
# span_processor = BatchSpanProcessor(OTLPSpanExporter())
# trace.get_tracer_provider().add_span_processor(span_processor)

from flask import Flask, request, jsonify

# Set up logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.post("/chat")
def chat():
    try:
        print("LLM output1:\n")
        payload = request.get_json(silent=True) or request.form
        llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.1, max_tokens=100)
        print("LLM output2:\n")
        messages = [
            SystemMessage(content="You are a helpful assistant!"),
            HumanMessage(content="What is the capital of France?"),
        ]
        print("LLM output3:\n")
        result = llm.invoke(messages).content
        print("LLM output:\n", result)
        # return result.content
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        str = f"Error processing chat request: {e}"
        return jsonify({str}), 500
    # from opentelemetry import  _logs
    # from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
    #     OTLPLogExporter,
    # )
    # from opentelemetry.sdk._logs import LoggerProvider
    # from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    # _logs.set_logger_provider(LoggerProvider())
    # _logs.get_logger_provider().add_log_record_processor(
    #     BatchLogRecordProcessor(OTLPLogExporter())
    # )
    # import logging
    # logger = logging.getLogger(__name__)
    # logging.basicConfig(level=logging.DEBUG)
    # logger.debug("OpenTelemetry instrumentation for LangChain encountered an error in $$$$$$$$$$$$$$$$")

if __name__ == "__main__":
    # When run directly: python app.py
    app.run(host="0.0.0.0", port=5003)