FROM python:3.12-slim

WORKDIR /app

# Copy the util-genai-dev package source
# Note: Build context should be the repository root
# docker build -f util/opentelemetry-util-genai-dev/examples/langgraph-mcp-weather-single-agent/Dockerfile .
COPY util/opentelemetry-util-genai-dev /app/opentelemetry-util-genai-dev

# Install opentelemetry-util-genai-dev from source
RUN pip install --no-cache-dir /app/opentelemetry-util-genai-dev

# Copy example files
COPY util/opentelemetry-util-genai-dev/examples/langgraph-mcp-weather-single-agent/requirements.txt .
COPY util/opentelemetry-util-genai-dev/examples/langgraph-mcp-weather-single-agent/main.py .
COPY util/opentelemetry-util-genai-dev/examples/langgraph-mcp-weather-single-agent/mcp_weather.py .

# Install example requirements
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "-u", "main.py"]
