# OpenAI Agents Instrumentation Examples

This directory contains examples of how to use the OpenAI Agents instrumentation.

## Files

- `quickstart.py` - Minimal OpenTelemetry setup and OpenAI chat sample.
- `basic_usage.py` - Tool-calling airline demo (no Azure Monitor).
- `mcp_hotel_capture_all.py` - MCP HTTP hotel finder sample (no Azure Monitor).
- `enhanced_travel_planner.py` - Complex orchestration travel planner (console exporter).
- `trace_collectors.py` - Showcase of Console, OTLP gRPC/HTTP, and Azure Monitor exporters.
- `.env.example` - Example environment variables configuration.

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
   python examples/quickstart.py
   ```

## Configuration

Content, metrics, and events are captured by default.

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
