"""
OpenTelemetry Tracing Demo with LangChain, LangGraph, and OpenAI

This example demonstrates how OpenTelemetry auto-instrumentation traces:
- Flask HTTP requests (creates root span for unified traces)
- LangChain operations (LLM calls, chains, tools)
- LangGraph workflow executions
- OpenAI API calls (chat completions)

The application uses Flask to provide a unified trace context:
1. GET /demo - Runs the full demo with agent and workflow
2. GET /agent - Runs just the ReAct agent with tools
3. All operations are automatically traced under the Flask request span

All operations are automatically traced and can be viewed in Jaeger.
This is a ZERO-CODE instrumentation example - no OpenTelemetry imports needed!
"""

import os
import random
from typing import Annotated

from flask import Flask, jsonify
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# Import create_react_agent - try new location first (LangGraph 1.0+), fall back to old
try:
    from langchain.agents import create_agent as create_react_agent
except ImportError:
    from langgraph.prebuilt import create_react_agent
from typing_extensions import TypedDict

app = Flask(__name__)


# ============================================================================
# Custom Tools
# ============================================================================


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: The name of the city to get weather for.

    Returns:
        A string describing the current weather conditions.
    """
    # Mock weather data
    weather_conditions = [
        ("sunny", 72, 45),
        ("cloudy", 65, 60),
        ("rainy", 58, 85),
        ("partly cloudy", 68, 55),
        ("windy", 62, 40),
    ]
    condition, temp, humidity = random.choice(weather_conditions)
    return f"The weather in {city} is {condition} with a temperature of {temp}F and {humidity}% humidity."


@tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression.

    Args:
        expression: A mathematical expression to evaluate (e.g., "2 + 2", "10 * 5").

    Returns:
        The result of the calculation as a string.
    """
    try:
        # Only allow safe mathematical operations
        allowed_chars = set("0123456789+-*/(). ")
        if not all(c in allowed_chars for c in expression):
            return "Error: Invalid characters in expression. Only numbers and +-*/() are allowed."

        result = eval(expression)  # Safe because we validated input
        return f"The result of {expression} is {result}"
    except Exception as e:
        return f"Error calculating '{expression}': {str(e)}"


@tool
def search_knowledge_base(query: str) -> str:
    """Search the knowledge base for information.

    Args:
        query: The search query to look up.

    Returns:
        Information found in the knowledge base.
    """
    # Mock knowledge base
    knowledge = {
        "python": "Python is a high-level, interpreted programming language known for its simplicity and readability. It was created by Guido van Rossum and first released in 1991.",
        "opentelemetry": "OpenTelemetry is an observability framework for cloud-native software. It provides a collection of tools, APIs, and SDKs for instrumenting, generating, collecting, and exporting telemetry data.",
        "langchain": "LangChain is a framework for developing applications powered by language models. It provides tools for prompt management, chains, agents, and memory.",
        "langgraph": "LangGraph is a library for building stateful, multi-actor applications with LLMs. It extends LangChain to enable cyclic computational graphs.",
    }

    query_lower = query.lower()
    for key, value in knowledge.items():
        if key in query_lower:
            return value

    return f"No specific information found for '{query}'. Try searching for: python, opentelemetry, langchain, or langgraph."


# List of all tools
tools = [get_weather, calculate, search_knowledge_base]


# ============================================================================
# LangGraph Workflow State
# ============================================================================


class WorkflowState(TypedDict):
    """State for the LangGraph workflow."""

    messages: Annotated[list, add_messages]
    query_metadata: dict  # preprocessor output (intent, entities, complexity)
    quality_score: float  # evaluator score (0-1)
    retry_count: int  # refinement attempts
    processing_steps: list  # track which nodes were visited
    final_answer: str


# ============================================================================
# Helper Functions
# ============================================================================


def get_llm():
    """Get configured ChatOpenAI instance."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    model = os.getenv("OPENAI_MODEL", "gpt-5.2-nano")
    return ChatOpenAI(model=model, temperature=0)


def create_agent_executor():
    """Create a ReAct agent with tools."""
    llm = get_llm()
    return create_react_agent(llm, tools)


def create_workflow():
    """Create a complex LangGraph workflow with multiple nodes for trace testing.

    Workflow structure:
    START → preprocessor → agent → (conditional) → tools → agent (loop)
                                        ↓
                                   evaluator → (conditional) → refiner → agent
                                        ↓
                                   formatter → END
    """
    llm = get_llm()

    # Build workflow
    workflow = StateGraph(WorkflowState)

    def preprocessor_node(state: WorkflowState) -> WorkflowState:
        """Analyze and enrich the input query with metadata."""
        messages = state.get("messages", [])
        if not messages:
            return {
                "query_metadata": {"intent": "unknown", "entities": [], "complexity": 0},
                "processing_steps": ["preprocessor"],
                "retry_count": 0,
                "quality_score": 0.0,
            }

        # Get the user's query
        user_message = messages[-1]
        query = user_message.content if hasattr(user_message, "content") else str(user_message)
        query_lower = query.lower()

        # Detect intent and entities
        intents = []
        entities = []

        if any(word in query_lower for word in ["weather", "temperature", "forecast"]):
            intents.append("weather")
            # Extract city names (simple heuristic)
            for city in ["paris", "tokyo", "london", "new york", "berlin"]:
                if city in query_lower:
                    entities.append({"type": "city", "value": city.title()})

        if any(word in query_lower for word in ["calculate", "math", "+", "-", "*", "/"]):
            intents.append("calculation")

        if any(word in query_lower for word in ["what is", "tell me about", "explain", "search"]):
            intents.append("research")
            for topic in ["python", "opentelemetry", "langchain", "langgraph"]:
                if topic in query_lower:
                    entities.append({"type": "topic", "value": topic})

        # Calculate complexity score
        complexity = min(1.0, len(intents) * 0.3 + len(entities) * 0.2)

        return {
            "query_metadata": {
                "intent": intents if intents else ["general"],
                "entities": entities,
                "complexity": complexity,
                "original_query": query,
            },
            "processing_steps": ["preprocessor"],
            "retry_count": 0,
            "quality_score": 0.0,
        }

    def agent_node(state: WorkflowState) -> WorkflowState:
        """Run the agent to process messages with tool binding."""
        llm_with_tools = llm.bind_tools(tools)
        response = llm_with_tools.invoke(state["messages"])

        # Track processing step
        steps = state.get("processing_steps", [])
        steps = list(steps) + ["agent"]

        return {
            "messages": [response],
            "processing_steps": steps,
        }

    def tool_node(state: WorkflowState) -> WorkflowState:
        """Execute tools based on agent's tool calls."""
        tool_node_executor = ToolNode(tools)
        result = tool_node_executor.invoke(state)

        # Track processing step
        steps = state.get("processing_steps", [])
        steps = list(steps) + ["tools"]

        return {
            **result,
            "processing_steps": steps,
        }

    def evaluator_node(state: WorkflowState) -> WorkflowState:
        """Assess response quality and completeness using LLM."""
        messages = state.get("messages", [])
        if not messages:
            return {"quality_score": 0.0, "processing_steps": state.get("processing_steps", []) + ["evaluator"]}

        last_message = messages[-1]
        response_content = last_message.content if hasattr(last_message, "content") else str(last_message)
        query_metadata = state.get("query_metadata", {})
        original_query = query_metadata.get("original_query", "")

        # Use LLM to evaluate response quality
        eval_prompt = f"""Evaluate the quality of this response on a scale of 0.0 to 1.0.

Original Query: {original_query}
Response: {response_content}

Consider:
- Completeness: Does it answer all parts of the query?
- Accuracy: Is the information correct?
- Clarity: Is the response clear and well-structured?

Respond with ONLY a number between 0.0 and 1.0, nothing else."""

        eval_response = llm.invoke([HumanMessage(content=eval_prompt)])
        eval_content = eval_response.content if hasattr(eval_response, "content") else str(eval_response)

        # Parse the quality score
        try:
            quality_score = float(eval_content.strip())
            quality_score = max(0.0, min(1.0, quality_score))
        except ValueError:
            # Default to moderate quality if parsing fails
            quality_score = 0.75

        steps = state.get("processing_steps", [])
        steps = list(steps) + ["evaluator"]

        return {
            "quality_score": quality_score,
            "processing_steps": steps,
        }

    def refiner_node(state: WorkflowState) -> WorkflowState:
        """Improve low-quality responses with additional context."""
        messages = state.get("messages", [])
        query_metadata = state.get("query_metadata", {})
        quality_score = state.get("quality_score", 0.0)
        retry_count = state.get("retry_count", 0)

        last_message = messages[-1] if messages else None
        response_content = ""
        if last_message:
            response_content = last_message.content if hasattr(last_message, "content") else str(last_message)

        original_query = query_metadata.get("original_query", "")

        # Create refinement prompt
        refine_prompt = f"""The previous response scored {quality_score:.2f} on quality.
Please improve this response to better answer the original query.

Original Query: {original_query}
Previous Response: {response_content}

Provide a more complete, accurate, and clear response. Focus on:
- Addressing all parts of the query
- Being more specific and detailed
- Ensuring accuracy of information"""

        refinement_message = HumanMessage(content=refine_prompt)

        steps = state.get("processing_steps", [])
        steps = list(steps) + ["refiner"]

        return {
            "messages": [refinement_message],
            "retry_count": retry_count + 1,
            "processing_steps": steps,
        }

    def formatter_node(state: WorkflowState) -> WorkflowState:
        """Format the final output with metadata."""
        messages = state.get("messages", [])
        query_metadata = state.get("query_metadata", {})
        quality_score = state.get("quality_score", 0.0)
        processing_steps = state.get("processing_steps", [])
        retry_count = state.get("retry_count", 0)

        last_message = messages[-1] if messages else None
        content = ""
        if last_message:
            content = last_message.content if hasattr(last_message, "content") else str(last_message)

        # Add processing metadata to final answer
        final_answer = f"""{content}

---
[Workflow Metadata]
- Quality Score: {quality_score:.2f}
- Retry Count: {retry_count}
- Processing Steps: {' → '.join(processing_steps + ['formatter'])}
- Detected Intents: {', '.join(query_metadata.get('intent', ['unknown']))}"""

        steps = list(processing_steps) + ["formatter"]

        return {
            "final_answer": final_answer,
            "processing_steps": steps,
        }

    def should_use_tools(state: WorkflowState) -> str:
        """Determine if we should use tools or proceed to evaluation."""
        messages = state.get("messages", [])
        if not messages:
            return "evaluate"

        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "evaluate"

    def should_refine(state: WorkflowState) -> str:
        """Determine if response needs refinement or can be formatted."""
        quality_score = state.get("quality_score", 0.0)
        retry_count = state.get("retry_count", 0)

        # Refine if quality is below threshold and we haven't exceeded retries
        if quality_score < 0.7 and retry_count < 2:
            return "refine"
        return "format"

    # Add nodes
    workflow.add_node("preprocessor", preprocessor_node)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("evaluator", evaluator_node)
    workflow.add_node("refiner", refiner_node)
    workflow.add_node("formatter", formatter_node)

    # Add edges
    workflow.add_edge(START, "preprocessor")
    workflow.add_edge("preprocessor", "agent")
    workflow.add_conditional_edges(
        "agent", should_use_tools, {"tools": "tools", "evaluate": "evaluator"}
    )
    workflow.add_edge("tools", "agent")
    workflow.add_conditional_edges(
        "evaluator", should_refine, {"refine": "refiner", "format": "formatter"}
    )
    workflow.add_edge("refiner", "agent")
    workflow.add_edge("formatter", END)

    return workflow.compile()


# ============================================================================
# Demo Functions
# ============================================================================


def run_agent_demo(query: str) -> dict:
    """Run the ReAct agent with a query."""
    print(f"\n{'='*60}")
    print(f"Running Agent Demo")
    print(f"Query: {query}")
    print(f"{'='*60}")

    agent = create_agent_executor()

    result = agent.invoke({"messages": [HumanMessage(content=query)]})

    final_message = result["messages"][-1]
    answer = final_message.content if hasattr(final_message, "content") else str(final_message)

    print(f"\nAgent Response: {answer}")

    return {
        "query": query,
        "answer": answer,
        "num_messages": len(result["messages"]),
    }


def run_workflow_demo(query: str) -> dict:
    """Run the LangGraph workflow with a query."""
    print(f"\n{'='*60}")
    print(f"Running Workflow Demo (Enhanced)")
    print(f"Query: {query}")
    print(f"{'='*60}")

    workflow = create_workflow()

    initial_state: WorkflowState = {
        "messages": [HumanMessage(content=query)],
        "query_metadata": {},
        "quality_score": 0.0,
        "retry_count": 0,
        "processing_steps": [],
        "final_answer": "",
    }

    result = workflow.invoke(initial_state)

    print(f"\nWorkflow Response: {result['final_answer']}")
    print(f"Quality Score: {result.get('quality_score', 'N/A')}")
    print(f"Processing Steps: {' → '.join(result.get('processing_steps', []))}")
    print(f"Retry Count: {result.get('retry_count', 0)}")

    return {
        "query": query,
        "answer": result["final_answer"],
        "quality_score": result.get("quality_score", 0.0),
        "retry_count": result.get("retry_count", 0),
        "processing_steps": result.get("processing_steps", []),
        "num_messages": len(result["messages"]),
    }


def run_full_demo() -> dict:
    """Run the complete demo showing all features."""
    print(f"\n{'='*60}")
    print("OpenTelemetry Tracing Demo: LangChain + LangGraph + OpenAI")
    print(f"{'='*60}")
    print("\nAll operations are being traced automatically!")
    print("View traces in Jaeger UI: http://localhost:16686")
    print(f"{'='*60}")

    results = {"status": "success", "steps": []}

    # Demo 1: Simple agent with weather tool
    print("\n--- Demo 1: Weather Query ---")
    weather_result = run_agent_demo(
        "Use the get_weather tool to check the weather in Paris and Tokyo."
    )
    results["weather_query"] = weather_result
    results["steps"].append("Weather query completed")

    # Demo 2: Agent with calculation
    print("\n--- Demo 2: Calculation Query ---")
    calc_result = run_agent_demo(
        "Use the calculate tool to compute 25 * 4 + 100 / 2"
    )
    results["calculation_query"] = calc_result
    results["steps"].append("Calculation query completed")

    # Demo 3: Agent with knowledge base search
    print("\n--- Demo 3: Knowledge Base Query ---")
    kb_result = run_agent_demo(
        "Use the search_knowledge_base tool to find information about OpenTelemetry and LangChain"
    )
    results["knowledge_query"] = kb_result
    results["steps"].append("Knowledge base query completed")

    # Demo 4: Complex multi-tool query via workflow
    print("\n--- Demo 4: Multi-Tool Workflow ---")
    workflow_result = run_workflow_demo(
        "Use the get_weather tool for New York weather, the calculate tool for 15 * 8, and search_knowledge_base for Python info."
    )
    results["workflow_query"] = workflow_result
    results["steps"].append("Multi-tool workflow completed")

    print(f"\n{'='*60}")
    print("Demo completed successfully!")
    print("Check Jaeger UI at http://localhost:16686 to view traces")
    print("Look for service: langchain-openai-demo")
    print(f"{'='*60}")

    return results


# ============================================================================
# Flask Routes
# ============================================================================


@app.route("/")
def index():
    """Home page with links to demos."""
    return """
    <h1>OpenTelemetry Tracing Demo</h1>
    <p>LangChain + LangGraph + OpenAI auto-instrumentation</p>
    <ul>
        <li><a href="/demo">Run Full Demo</a> - Execute all demo scenarios</li>
        <li><a href="/agent">Run Agent Demo</a> - Run just the ReAct agent</li>
        <li><a href="/workflow">Run Workflow Demo</a> - Run the LangGraph workflow</li>
        <li><a href="http://localhost:16686" target="_blank">Jaeger UI</a> - View traces</li>
    </ul>
    <p>All operations are automatically traced with OpenTelemetry!</p>
    <h2>Features Demonstrated:</h2>
    <ul>
        <li><b>LangChain</b>: LLM calls, tool execution, ReAct agent</li>
        <li><b>LangGraph</b>: Stateful workflow with conditional routing</li>
        <li><b>OpenAI</b>: Chat completions with tool use</li>
        <li><b>Tools</b>: Weather lookup, calculator, knowledge base search</li>
    </ul>
    """


@app.route("/demo")
def demo():
    """Run the full demo and return results as JSON."""
    results = run_full_demo()
    return jsonify(results)


@app.route("/agent")
def agent():
    """Run a single agent query."""
    # Use explicit tool-requiring queries to ensure tools get called
    query = "Use the get_weather tool to check the weather in London, then use the calculate tool to compute 100 + 200"
    result = run_agent_demo(query)
    return jsonify(result)


@app.route("/workflow")
def workflow():
    """Run a single workflow query."""
    # Use explicit tool-requiring queries to ensure tools get called
    query = "Use the get_weather tool to check weather in Berlin, then use search_knowledge_base tool to find information about LangGraph."
    result = run_workflow_demo(query)
    return jsonify(result)


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


# ============================================================================
# Main
# ============================================================================


def main():
    """Main function to run the Flask app."""
    print(f"{'='*60}")
    print("OpenTelemetry Tracing Demo Server")
    print("LangChain + LangGraph + OpenAI")
    print(f"{'='*60}")
    print("\nStarting Flask server...")
    print("Visit http://localhost:5000/demo to run the demo")
    print("View traces in Jaeger UI: http://localhost:16686")
    print(f"{'='*60}")

    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
