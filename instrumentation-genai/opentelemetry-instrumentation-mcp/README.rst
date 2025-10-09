# MCP Instrumentor

OpenTelemetry instrumentation for Model Context Protocol (MCP).

## Installation

```bash
pip install opentelemetry-instrumentation-mcp
```

## Usage

Automatically enabled with:

```bash
opentelemetry-instrument python your_mcp_app.py
```

## Configuration

## Spans Created

- **Client**: 
  - Initialize: `mcp.initialize`
  - List Tools: `mcp.list_tools`
  - Call Tool: `mcp.call_tool.{tool_name}`
- **Server**: `tools/initialize`, `tools/list`, `tools/{tool_name}`