# OpenAI Agents Instrumentation Examples

This directory contains examples of how to use the OpenAI Agents instrumentation.

## Files

- `basic_usage.py` - Basic example showing how to enable and use the instrumentation
- `.env.example` - Example environment variables configuration

## Basic Usage

1. Install the package:
   ```bash
   pip install opentelemetry-instrumentation-openai-agents
   ```

2. Set up your environment variables (copy `.env.example` to `.env` and modify as needed):
   ```bash
   cp .env.example .env
   ```

3. Run the basic example:
   ```bash
   python basic_usage.py
   ```

## Configuration

The instrumentation can be configured using environment variables:

- `OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_CONTENT` - Enable/disable content capture (default: false)
- `OTEL_INSTRUMENTATION_OPENAI_AGENTS_CAPTURE_METRICS` - Enable/disable metrics collection (default: true)

## Integration with Agent Frameworks

This instrumentation is designed to work with OpenAI-based agent frameworks. Common use cases include:

- Multi-agent systems
- Conversational AI applications
- Automated reasoning systems
- Task-oriented agents

## Observability Features

The instrumentation provides:

- **Distributed tracing** - Track requests across agent interactions
- **Metrics collection** - Monitor token usage, latency, and error rates
- **Content capture** - Optional logging of request/response content
- **Error tracking** - Automatic error status recording

## Security Considerations

When enabling content capture, be aware that:

- Request and response content may contain sensitive information
- Content is included in telemetry data
- Ensure your telemetry backend has appropriate security measures
- Consider data retention policies for captured content
