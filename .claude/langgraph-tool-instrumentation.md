# LangGraph Tool Instrumentation

This document describes the tool instrumentation enhancements made to the `opentelemetry-instrumentation-langgraph` package.

## Overview

Added tool call tracing to the LangGraph instrumentation, enabling visibility into individual tool executions within LangGraph workflows.

**Package**: `opentelemetry-instrumentation-langgraph`
**Location**: `instrumentation-genai/opentelemetry-instrumentation-langgraph/`

---

## Features

### Tool Node Instrumentation

The instrumentation wraps `ToolNode` from `langgraph.prebuilt` to capture:
- When tools are executed
- Which tools were called
- Tool input arguments
- Tool output results
- Execution errors

### Methods Wrapped

| Class | Method | Description |
|-------|--------|-------------|
| `ToolNode` | `_func` | Synchronous tool execution |
| `ToolNode` | `_afunc` | Asynchronous tool execution |

---

## Span Hierarchy

```
langgraph.workflow {graph_name}        [workflow span]
└── langgraph.tool_node                [tool node span]
    ├── {tool_name}.tool               [individual tool span]
    ├── {tool_name}.tool               [individual tool span]
    └── ...
```

---

## Span Attributes

### ToolNode Span (`langgraph.tool_node`)

| Attribute | Description | Type |
|-----------|-------------|------|
| `langgraph.node.name` | Node name (default: "tools") | string |
| `langgraph.tool.count` | Number of tools being executed | int |
| `traceloop.span.kind` | Span kind (value: "task") | string |

### Individual Tool Span (`{tool_name}.tool`)

| Attribute | Description | Type |
|-----------|-------------|------|
| `langgraph.tool.name` | Tool function name | string |
| `langgraph.tool.call_id` | Tool call ID from the message | string |
| `langgraph.tool.input` | JSON-serialized input arguments | string (JSON) |
| `langgraph.tool.output` | JSON-serialized output result | string (JSON) |
| `traceloop.span.kind` | Span kind (value: "tool") | string |
| `gen_ai.operation.name` | Operation name (value: "execute_tool") | string |

---

## Semantic Attributes

New constants added to `patch.py`:

```python
# Tool-related semantic attributes
LANGGRAPH_TOOL_NAME = "langgraph.tool.name"
LANGGRAPH_TOOL_CALL_ID = "langgraph.tool.call_id"
LANGGRAPH_TOOL_COUNT = "langgraph.tool.count"
LANGGRAPH_TOOL_INPUT = "langgraph.tool.input"
LANGGRAPH_TOOL_OUTPUT = "langgraph.tool.output"

# Traceloop semantic attributes (for compatibility with LangChain)
TRACELOOP_SPAN_KIND = "traceloop.span.kind"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
```

---

## Files Modified

| File | Changes |
|------|---------|
| `patch.py` | Added tool semantic attributes, helper functions, and wrapper functions |
| `__init__.py` | Added ToolNode wrapping in `_instrument()` and `_uninstrument()` |

### New Functions in `patch.py`

| Function | Description |
|----------|-------------|
| `_safe_json_serialize(obj)` | Safely serialize objects to JSON |
| `_get_tool_name(tool_call)` | Extract tool name from tool call |
| `_get_tool_call_id(tool_call)` | Extract tool call ID |
| `_get_tool_args(tool_call)` | Extract tool arguments |
| `create_tool_node_wrapper(tracer)` | Wrapper for sync `ToolNode._func` |
| `create_async_tool_node_wrapper(tracer)` | Wrapper for async `ToolNode._afunc` |
| `_record_tool_spans(tracer, tool_calls, results)` | Record individual tool spans |

---

## Example Usage

```python
from opentelemetry.instrumentation.langgraph import LangGraphInstrumentor
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt.tool_node import ToolNode

# Instrument before importing/using LangGraph
LangGraphInstrumentor().instrument()

# Define tools
@tool
def search(query: str) -> str:
    """Search the web for information."""
    return f"Results for: {query}"

@tool
def calculate(expression: str) -> str:
    """Calculate a mathematical expression."""
    return str(eval(expression))

# Create ToolNode
tools = [search, calculate]
tool_node = ToolNode(tools)

# Build graph with tools
graph = StateGraph(State)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)
graph.add_edge(START, "agent")
graph.add_edge("agent", "tools")
graph.add_edge("tools", END)

# Run - spans will be automatically created
compiled = graph.compile()
result = compiled.invoke({"messages": []})
```

---

## Example Trace Output

When running a LangGraph workflow with tools, you'll see spans like:

```
Span: langgraph.workflow LangGraph
  langgraph.graph.name: LangGraph

Span: langgraph.tool_node
  langgraph.node.name: tools
  langgraph.tool.count: 2
  traceloop.span.kind: task

Span: search.tool
  langgraph.tool.name: search
  langgraph.tool.call_id: call_1
  langgraph.tool.input: {"query": "weather"}
  langgraph.tool.output: "Results for: weather"
  traceloop.span.kind: tool
  gen_ai.operation.name: execute_tool

Span: calculate.tool
  langgraph.tool.name: calculate
  langgraph.tool.call_id: call_2
  langgraph.tool.input: {"expression": "2+2"}
  langgraph.tool.output: "4"
  traceloop.span.kind: tool
  gen_ai.operation.name: execute_tool
```

---

## Error Handling

- Instrumentation errors are caught and logged without affecting the application
- Tool execution errors are recorded on spans with `StatusCode.ERROR`
- Exceptions are recorded using `span.record_exception(e)`

---

## Compatibility

- **LangGraph**: >= 0.2.0
- **OpenTelemetry API**: ~= 1.31
- **OpenTelemetry Instrumentation**: ~= 0.57b0
- **Python**: >= 3.10
