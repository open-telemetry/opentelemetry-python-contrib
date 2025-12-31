OpenTelemetry LangGraph Instrumentation
=======================================

|pypi|

.. |pypi| image:: https://badge.fury.io/py/opentelemetry-instrumentation-langgraph.svg
   :target: https://pypi.org/project/opentelemetry-instrumentation-langgraph/

This library allows tracing LangGraph workflow executions with OpenTelemetry.
Supports LangGraph 0.2.0+ including LangGraph 1.0.

Installation
------------

::

    pip install opentelemetry-instrumentation-langgraph

Usage
-----

Manual Instrumentation
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from opentelemetry.instrumentation.langgraph import LangGraphInstrumentor
    from langgraph.graph import StateGraph, START, END
    from typing import TypedDict

    # Enable instrumentation
    LangGraphInstrumentor().instrument()

    # Define your graph
    class State(TypedDict):
        value: str

    def process_node(state: State) -> dict:
        return {"value": state["value"] + " processed"}

    graph = StateGraph(State)
    graph.add_node("process", process_node)
    graph.add_edge(START, "process")
    graph.add_edge("process", END)

    # Use your graph
    compiled = graph.compile()
    result = compiled.invoke({"value": "hello"})

    # Disable instrumentation
    LangGraphInstrumentor().uninstrument()

Zero-Code Instrumentation
~~~~~~~~~~~~~~~~~~~~~~~~~

Run your application with the ``opentelemetry-instrument`` command:

::

    opentelemetry-instrument python your_app.py

Features
--------

- Automatic span creation for workflow invocations
- Support for sync (``invoke``) and async (``ainvoke``) operations
- Streaming support (``stream`` and ``astream``) with stream mode capture
- Batch operations (``batch`` and ``abatch``)
- State operations (``get_state``, ``update_state``) for human-in-the-loop visibility
- Tool node execution tracing
- ``create_react_agent`` instrumentation (from both ``langgraph.prebuilt`` and ``langchain.agents``)
- Graph name and ID capture in span attributes
- Duration metrics for workflow executions

Span Attributes
---------------

The instrumentation captures the following span attributes:

Graph Attributes
~~~~~~~~~~~~~~~~

- ``langgraph.graph.name``: The name of the graph being executed
- ``langgraph.graph.id``: The graph ID (if available)

Stream Attributes
~~~~~~~~~~~~~~~~~

- ``langgraph.stream.mode``: The stream mode used (values, updates, messages, checkpoints, tasks, debug)
- ``langgraph.step``: The number of chunks streamed

Batch Attributes
~~~~~~~~~~~~~~~~

- ``langgraph.batch.size``: The number of inputs in the batch

Tool Attributes
~~~~~~~~~~~~~~~

- ``langgraph.tool.name``: Name of the tool being executed
- ``langgraph.tool.call_id``: The tool call ID
- ``langgraph.tool.count``: Number of tools in a tool node
- ``langgraph.tool.input``: Tool input arguments (JSON)
- ``langgraph.tool.output``: Tool output (JSON)

Agent Attributes
~~~~~~~~~~~~~~~~

- ``langgraph.agent.model``: The model used by the agent
- ``langgraph.agent.tools_count``: Number of tools available to the agent
- ``langgraph.agent.has_checkpointer``: Whether the agent has persistence enabled

State Operation Attributes
~~~~~~~~~~~~~~~~~~~~~~~~~~

- ``langgraph.state.operation``: The state operation type (get_state, update_state, etc.)

Metrics
-------

The instrumentation also provides the following metrics:

- ``langgraph.workflow.duration``: Histogram of workflow execution duration in seconds

References
----------

* `OpenTelemetry LangGraph Instrumentation <https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/langgraph/langgraph.html>`_
* `OpenTelemetry Project <https://opentelemetry.io/>`_
* `LangGraph Documentation <https://langchain-ai.github.io/langgraph/>`_
