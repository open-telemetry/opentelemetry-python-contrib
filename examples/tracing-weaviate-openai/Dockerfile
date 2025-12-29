FROM python:3.11-slim

WORKDIR /otel-contrib

# Install build dependencies and curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# First install released PyPI versions of core packages
# Using 0.58b0 versions to match OpenAI instrumentation requirements
RUN pip install \
    opentelemetry-api~=1.37 \
    opentelemetry-sdk~=1.37 \
    opentelemetry-instrumentation~=0.58b0 \
    opentelemetry-semantic-conventions~=0.58b0 \
    opentelemetry-distro~=0.58b0 \
    opentelemetry-exporter-otlp-proto-grpc~=1.37 \
    opentelemetry-instrumentation-flask~=0.58b0 \
    opentelemetry-instrumentation-httpx~=0.58b0 \
    opentelemetry-instrumentation-requests~=0.58b0 \
    opentelemetry-instrumentation-urllib3~=0.58b0 \
    wrapt>=1.0.0 \
    openai>=1.26.0 \
    weaviate-client>=4.0.0 \
    flask \
    httpx \
    requests

# Copy the entire repository
COPY . /otel-contrib

# Install local instrumentation packages (they will use already-installed dependencies)
# OpenAI instrumentation
RUN pip install --no-deps -e /otel-contrib/instrumentation-genai/opentelemetry-instrumentation-openai-v2

# Weaviate instrumentation
RUN pip install --no-deps -e /otel-contrib/instrumentation-genai/opentelemetry-instrumentation-weaviate

# Set working directory to app
WORKDIR /app

# Copy application code
COPY examples/tracing-weaviate-openai/app /app

# Run with auto-instrumentation
CMD ["opentelemetry-instrument", "python", "main.py"]
