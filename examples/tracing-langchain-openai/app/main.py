"""
OpenTelemetry Tracing Demo with LangChain Reflexion Pattern

This example demonstrates OpenTelemetry instrumentation for the Reflexion
pattern - an architecture where an agent reflects on its responses, critiques
them, and iteratively improves with additional research.

The Reflexion pattern (Shinn et al.) enables:
1. Initial answer generation with self-reflection
2. Self-critique to identify gaps and improvements
3. Research via search queries to gather more information
4. Iterative revision with citations

All operations are traced and can be viewed in Jaeger.
"""

# Explicitly instrument LangGraph BEFORE importing it
# This ensures all hooks are in place before module loading
from opentelemetry.instrumentation.langgraph import LangGraphInstrumentor
LangGraphInstrumentor().instrument()

import datetime
import json
import os
from typing import Annotated

from flask import Flask, jsonify
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field, ValidationError
from typing_extensions import TypedDict

app = Flask(__name__)


# ============================================================================
# Reflexion Pattern Models
# ============================================================================


class Reflection(BaseModel):
    """Self-critique of an answer."""

    missing: str = Field(description="Critique of what is missing from the answer.")
    superfluous: str = Field(description="Critique of what is superfluous in the answer.")


class AnswerQuestion(BaseModel):
    """Answer the question with self-reflection and search queries for improvement."""

    answer: str = Field(description="~250 word detailed answer to the question.")
    reflection: Reflection = Field(description="Your reflection on the initial answer.")
    search_queries: list[str] = Field(
        description="1-3 search queries for researching improvements to address the critique."
    )


class ReviseAnswer(AnswerQuestion):
    """Revise your original answer with citations from research."""

    references: list[str] = Field(
        description="Citations motivating your updated answer."
    )


class ReflexionState(TypedDict):
    """State for the Reflexion workflow."""

    messages: Annotated[list, add_messages]


# ============================================================================
# Helper Functions
# ============================================================================


def get_llm():
    """Get configured ChatOpenAI instance."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return ChatOpenAI(model=model, temperature=0)


# ============================================================================
# Reflexion Pattern Components
# ============================================================================


class ResponderWithRetries:
    """A responder that retries on validation errors for structured output."""

    def __init__(self, runnable, validator):
        self.runnable = runnable
        self.validator = validator

    def respond(self, state: dict):
        """Generate a response, retrying up to 3 times on validation errors."""
        response = []
        for attempt in range(3):
            response = self.runnable.invoke(
                {"messages": state["messages"]}, {"tags": [f"attempt:{attempt}"]}
            )
            try:
                self.validator.invoke(response)
                return {"messages": response}
            except ValidationError as e:
                state["messages"] = state["messages"] + [
                    response,
                    ToolMessage(
                        content=f"{repr(e)}\n\nPay close attention to the function schema.\n\n"
                        + self.validator.schema_json()
                        + " Respond by fixing all validation errors.",
                        tool_call_id=response.tool_calls[0]["id"],
                    ),
                ]
        return {"messages": response}


def run_mock_search(search_queries: list[str]) -> list[list[dict]]:
    """Mock search function returning pre-defined results for demo purposes.

    In a real application, this would call a search API like Tavily or Google.
    """
    mock_results = {
        "climate": [
            {
                "title": "IPCC Climate Report 2023",
                "url": "https://www.ipcc.ch/report/ar6/",
                "content": "The Intergovernmental Panel on Climate Change reports that limiting warming to 1.5°C requires rapid, deep and sustained greenhouse gas emissions reductions. Global net zero CO2 emissions need to be achieved by 2050.",
            },
            {
                "title": "Climate Action Strategies",
                "url": "https://www.un.org/climatechange",
                "content": "Key strategies include transitioning to renewable energy, improving energy efficiency, protecting and restoring ecosystems, sustainable agriculture, and carbon capture technologies.",
            },
        ],
        "renewable": [
            {
                "title": "Renewable Energy Statistics 2023",
                "url": "https://www.irena.org/statistics",
                "content": "Solar and wind power capacity grew by 295 GW in 2022, a 12% increase. Renewables now account for 30% of global electricity generation.",
            },
        ],
        "carbon": [
            {
                "title": "Carbon Capture Technology",
                "url": "https://www.energy.gov/carbon-capture",
                "content": "Carbon capture and storage (CCS) can reduce emissions from power plants by up to 90%. Direct air capture technologies are also advancing rapidly.",
            },
        ],
        "policy": [
            {
                "title": "Climate Policy Framework",
                "url": "https://www.wri.org/climate-policy",
                "content": "Effective climate policies include carbon pricing, renewable portfolio standards, building codes, and investment in clean technology R&D.",
            },
        ],
        "default": [
            {
                "title": "General Research Result",
                "url": "https://example.com/research",
                "content": "This is a mock search result for demonstration purposes. In production, this would return real search results from a search API.",
            },
        ],
    }

    results = []
    for query in search_queries:
        query_lower = query.lower()
        found = False
        for keyword, result_list in mock_results.items():
            if keyword in query_lower:
                results.append(result_list)
                found = True
                break
        if not found:
            results.append(mock_results["default"])

    return results


def create_reflexion_workflow():
    """Create a Reflexion workflow for self-critique and iterative improvement.

    The Reflexion pattern (Shinn et al.) enables an agent to:
    1. Generate an initial answer with self-reflection
    2. Research improvements based on critique
    3. Revise the answer with citations

    Workflow structure:
    START → draft → execute_tools → revise → (loop back or END)
    """
    llm = get_llm()
    max_iterations = 5

    # Create the actor prompt template
    actor_prompt_template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are an expert researcher.
Current time: {time}

1. {first_instruction}
2. Reflect and critique your answer. Be severe to maximize improvement.
3. Recommend search queries to research information and improve your answer.""",
            ),
            MessagesPlaceholder(variable_name="messages"),
            (
                "user",
                "\n\n<system>Reflect on the user's original question and the"
                " actions taken thus far. Respond using the {function_name} function.</reminder>",
            ),
        ]
    ).partial(
        time=lambda: datetime.datetime.now().isoformat(),
    )

    # Initial answer chain
    initial_answer_chain = actor_prompt_template.partial(
        first_instruction="Provide a detailed ~250 word answer.",
        function_name=AnswerQuestion.__name__,
    ) | llm.bind_tools(tools=[AnswerQuestion])

    validator = PydanticToolsParser(tools=[AnswerQuestion])
    first_responder = ResponderWithRetries(
        runnable=initial_answer_chain, validator=validator
    )

    # Revision chain
    revise_instructions = """Revise your previous answer using the new information.
    - You should use the previous critique to add important information to your answer.
        - You MUST include numerical citations in your revised answer to ensure it can be verified.
        - Add a "References" section to the bottom of your answer (which does not count towards the word limit). In form of:
            - [1] https://example.com
            - [2] https://example.com
    - You should use the previous critique to remove superfluous information from your answer and make SURE it is not more than 250 words.
"""

    revision_chain = actor_prompt_template.partial(
        first_instruction=revise_instructions,
        function_name=ReviseAnswer.__name__,
    ) | llm.bind_tools(tools=[ReviseAnswer])

    revision_validator = PydanticToolsParser(tools=[ReviseAnswer])
    revisor = ResponderWithRetries(runnable=revision_chain, validator=revision_validator)

    # Create tool node for running search queries
    def run_queries(search_queries: list[str], **kwargs):
        """Run the generated search queries."""
        return run_mock_search(search_queries)

    tool_node = ToolNode(
        [
            StructuredTool.from_function(run_queries, name=AnswerQuestion.__name__),
            StructuredTool.from_function(run_queries, name=ReviseAnswer.__name__),
        ]
    )

    # Build the workflow
    builder = StateGraph(ReflexionState)
    builder.add_node("draft", first_responder.respond)
    builder.add_node("execute_tools", tool_node)
    builder.add_node("revise", revisor.respond)

    # Add edges
    builder.add_edge("draft", "execute_tools")
    builder.add_edge("execute_tools", "revise")

    def _get_num_iterations(state: ReflexionState) -> int:
        """Count the number of iterations (AI + tool message pairs)."""
        i = 0
        for m in state["messages"][::-1]:
            if hasattr(m, "type") and m.type not in {"tool", "ai"}:
                break
            i += 1
        return i

    def event_loop(state: ReflexionState) -> str:
        """Determine whether to continue iterating or end."""
        num_iterations = _get_num_iterations(state)
        if num_iterations > max_iterations:
            return END
        return "execute_tools"

    builder.add_conditional_edges("revise", event_loop, ["execute_tools", END])
    builder.add_edge(START, "draft")

    return builder.compile()


# ============================================================================
# Demo Function
# ============================================================================


def run_reflexion_demo(query: str) -> dict:
    """Run the Reflexion workflow with self-critique and iterative improvement.

    The Reflexion pattern demonstrates:
    1. Initial draft with self-reflection
    2. Mock research based on critique
    3. Revised answer with citations
    4. Multiple iteration cycles for improvement
    """
    print(f"\n{'='*60}")
    print("Running Reflexion Demo (Self-Critique & Improvement)")
    print(f"Query: {query}")
    print(f"{'='*60}")

    workflow = create_reflexion_workflow()

    initial_state: ReflexionState = {
        "messages": [HumanMessage(content=query)],
    }

    # Stream the workflow to see each step
    events = list(workflow.stream(initial_state, stream_mode="values"))

    # Get the final result
    final_result = events[-1] if events else {"messages": []}
    messages = final_result.get("messages", [])

    # Extract the final answer from the last AI message with tool calls
    final_answer = ""
    for msg in reversed(messages):
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_call = msg.tool_calls[0]
            if "answer" in tool_call.get("args", {}):
                final_answer = tool_call["args"]["answer"]
                if "references" in tool_call.get("args", {}):
                    references = tool_call["args"]["references"]
                    if references:
                        final_answer += "\n\nReferences:\n" + "\n".join(
                            f"[{i+1}] {ref}" for i, ref in enumerate(references)
                        )
                break

    print(f"\nReflexion Response: {final_answer[:500]}..." if len(final_answer) > 500 else f"\nReflexion Response: {final_answer}")
    print(f"Total Messages: {len(messages)}")
    print(f"Iterations: {len(events)}")

    return {
        "query": query,
        "answer": final_answer,
        "num_messages": len(messages),
        "num_iterations": len(events),
    }


# ============================================================================
# Flask Routes
# ============================================================================


@app.route("/")
def index():
    """Home page with links to demos."""
    return """
    <h1>OpenTelemetry Tracing Demo - Reflexion Pattern</h1>
    <p>LangChain + LangGraph + OpenAI auto-instrumentation</p>
    <ul>
        <li><a href="/reflexion">Run Reflexion Demo</a> - Self-critique and iterative improvement</li>
        <li><a href="http://localhost:16686" target="_blank">Jaeger UI</a> - View traces</li>
    </ul>
    <p>All operations are automatically traced with OpenTelemetry!</p>
    <h2>Reflexion Pattern Features:</h2>
    <ul>
        <li><b>Draft</b>: Initial answer generation with self-reflection</li>
        <li><b>Critique</b>: Identifies missing and superfluous content</li>
        <li><b>Research</b>: Generates search queries to improve answer</li>
        <li><b>Revise</b>: Updates answer with citations from research</li>
        <li><b>Iterate</b>: Loops until quality is satisfactory</li>
    </ul>
    """


@app.route("/reflexion")
def reflexion():
    """Run the Reflexion demo - self-critique and iterative improvement.

    This demonstrates the Reflexion pattern from Shinn et al., where an agent:
    1. Generates an initial answer with self-reflection
    2. Critiques its own response
    3. Researches improvements based on the critique
    4. Revises the answer with citations
    5. Iterates until quality is satisfactory
    """
    query = "How should we handle the climate crisis?"
    result = run_reflexion_demo(query)
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
    print("OpenTelemetry Tracing Demo Server - Reflexion Pattern")
    print("LangChain + LangGraph + OpenAI")
    print(f"{'='*60}")
    print("\nStarting Flask server...")
    print("Visit http://localhost:5000/reflexion to run the demo")
    print("View traces in Jaeger UI: http://localhost:16686")
    print(f"{'='*60}")

    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
