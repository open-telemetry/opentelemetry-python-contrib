from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

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

# configure logging
_logs.set_logger_provider(LoggerProvider())
_logs.get_logger_provider().add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter())
)

# configure metrics
metrics.set_meter_provider(
    MeterProvider(
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(),
            ),
        ]
    )
)


def main():
    # Set up instrumentation
    LangChainInstrumentor().instrument()

    # ChatOpenAI
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

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = llm.invoke(messages)

    print("LLM output:\n", result)

    # Un-instrument after use
    LangChainInstrumentor().uninstrument()


if __name__ == "__main__":
    main()
