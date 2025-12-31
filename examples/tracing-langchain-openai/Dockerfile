FROM python:3.11-slim

WORKDIR /otel-contrib

# Install build dependencies and curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# First install released PyPI versions of core packages
RUN pip install \
    opentelemetry-api~=1.37 \
    opentelemetry-sdk~=1.37 \
    opentelemetry-instrumentation~=0.58b0 \
    opentelemetry-semantic-conventions~=0.58b0 \
    opentelemetry-distro~=0.58b0 \
    opentelemetry-exporter-otlp-proto-grpc~=1.37 \
    opentelemetry-instrumentation-flask~=0.58b0 \
    wrapt>=1.0.0 \
    langchain>=0.3.21 \
    langchain-core>=0.3.21 \
    langchain-openai>=0.2.0 \
    langgraph>=0.2.0 \
    flask

# Copy the entire repository
COPY . /otel-contrib

# Install local instrumentation packages (they will use already-installed dependencies)
# OpenAI instrumentation
RUN pip install --no-deps -e /otel-contrib/instrumentation-genai/opentelemetry-instrumentation-openai-v2

# LangChain instrumentation
RUN pip install --no-deps -e /otel-contrib/instrumentation-genai/opentelemetry-instrumentation-langchain

# LangGraph instrumentation
RUN pip install --no-deps -e /otel-contrib/instrumentation-genai/opentelemetry-instrumentation-langgraph

# Set working directory to app
WORKDIR /app

# Copy application code
COPY examples/tracing-langchain-openai/app /app

# Run with auto-instrumentation
CMD ["opentelemetry-instrument", "python", "main.py"]
