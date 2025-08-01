from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.langchain import LangChainInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure tracing
trace.set_tracer_provider(TracerProvider())
span_processor = BatchSpanProcessor(OTLPSpanExporter())
trace.get_tracer_provider().add_span_processor(span_processor)

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
