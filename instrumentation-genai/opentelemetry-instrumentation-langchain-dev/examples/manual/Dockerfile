FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create token cache directory with proper permissions
RUN mkdir -p /tmp && chmod 755 /tmp

# Copy requirements first for better caching
COPY opentelemetry-instrumentation-langchain/examples/manual/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data for sentiment analysis (optional)
RUN python -c "import nltk; nltk.download('vader_lexicon', download_dir='/usr/local/nltk_data')" || true

# Copy the local packages source code (util-genai + instrumentation)
# Legacy opentelemetry-genai-sdk removed.
COPY opentelemetry-util-genai /tmp/opentelemetry-util-genai
COPY opentelemetry-instrumentation-langchain /tmp/opentelemetry-instrumentation-langchain

# Install local packages in editable mode
RUN pip install -e /tmp/opentelemetry-util-genai
RUN pip install -e /tmp/opentelemetry-instrumentation-langchain

# Copy application code
COPY opentelemetry-instrumentation-langchain/examples/manual/main.py .

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Run the application
ENTRYPOINT ["python", "main.py"]
