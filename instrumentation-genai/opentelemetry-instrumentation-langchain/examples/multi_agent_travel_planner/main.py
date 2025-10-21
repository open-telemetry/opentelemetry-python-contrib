# Copyright The OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Multi-agent travel planner driven by LangGraph.

The example coordinates a set of LangChain agents that collaborate to build a
week-long city break itinerary.  OpenTelemetry spans are produced for both the
overall orchestration and each LLM/tool call so you can inspect the traces in
your OTLP collector.
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from typing import Annotated, Dict, List, Optional, TypedDict
from uuid import uuid4

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages

try:  # LangChain >= 1.0.0
    from langchain.agents import (
        create_agent as _create_react_agent,  # type: ignore[attr-defined]
    )
except (
    ImportError
):  # pragma: no cover - compatibility with older LangGraph releases
    from langgraph.prebuilt import (
        create_react_agent as _create_react_agent,  # type: ignore[assignment]
    )

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.langchain import LangChainInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind

# ---------------------------------------------------------------------------
# Sample data utilities
# ---------------------------------------------------------------------------


DESTINATIONS = {
    "paris": {
        "country": "France",
        "currency": "EUR",
        "airport": "CDG",
        "highlights": [
            "Eiffel Tower at sunset",
            "Seine dinner cruise",
            "Day trip to Versailles",
        ],
    },
    "tokyo": {
        "country": "Japan",
        "currency": "JPY",
        "airport": "HND",
        "highlights": [
            "Tsukiji market food tour",
            "Ghibli Museum visit",
            "Day trip to Hakone hot springs",
        ],
    },
    "rome": {
        "country": "Italy",
        "currency": "EUR",
        "airport": "FCO",
        "highlights": [
            "Colosseum underground tour",
            "Private pasta masterclass",
            "Sunset walk through Trastevere",
        ],
    },
}


def _pick_destination(user_request: str) -> str:
    lowered = user_request.lower()
    for name in DESTINATIONS:
        if name in lowered:
            return name.title()
    return "Paris"


def _pick_origin(user_request: str) -> str:
    lowered = user_request.lower()
    for city in ["seattle", "new york", "san francisco", "london"]:
        if city in lowered:
            return city.title()
    return "Seattle"


def _compute_dates() -> tuple[str, str]:
    start = datetime.now() + timedelta(days=30)
    end = start + timedelta(days=7)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Tools exposed to agents
# ---------------------------------------------------------------------------


@tool
def mock_search_flights(origin: str, destination: str, departure: str) -> str:
    """Return mock flight options for a given origin/destination pair."""
    random.seed(hash((origin, destination, departure)) % (2**32))
    airline = random.choice(["SkyLine", "AeroJet", "CloudNine"])
    fare = random.randint(700, 1250)
    return (
        f"Top choice: {airline} non-stop service {origin}->{destination}, "
        f"depart {departure} 09:15, arrive {departure} 17:05. "
        f"Premium economy fare ${fare} return."
    )


@tool
def mock_search_hotels(destination: str, check_in: str, check_out: str) -> str:
    """Return mock hotel recommendation for the stay."""
    random.seed(hash((destination, check_in, check_out)) % (2**32))
    name = random.choice(["Grand Meridian", "Hotel Lumière", "The Atlas"])
    rate = random.randint(240, 410)
    return (
        f"{name} near the historic centre. Boutique suites, rooftop bar, "
        f"average nightly rate ${rate} including breakfast."
    )


@tool
def mock_search_activities(destination: str) -> str:
    """Return a short list of signature activities for the destination."""
    data = DESTINATIONS.get(destination.lower(), DESTINATIONS["paris"])
    bullets = "\n".join(f"- {item}" for item in data["highlights"])
    return f"Signature experiences in {destination.title()}:\n{bullets}"


# ---------------------------------------------------------------------------
# LangGraph state & helpers
# ---------------------------------------------------------------------------


class PlannerState(TypedDict):
    """Shared state that moves through the LangGraph workflow."""

    messages: Annotated[List[AnyMessage], add_messages]
    user_request: str
    session_id: str
    origin: str
    destination: str
    departure: str
    return_date: str
    travellers: int
    flight_summary: Optional[str]
    hotel_summary: Optional[str]
    activities_summary: Optional[str]
    final_itinerary: Optional[str]
    current_agent: str


def _model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _create_llm(
    agent_name: str, *, temperature: float, session_id: str
) -> ChatOpenAI:
    """Create an LLM instance decorated with tags/metadata for tracing."""
    model = _model_name()
    tags = [f"agent:{agent_name}", "travel-planner"]
    metadata = {
        "agent_name": agent_name,
        "agent_type": agent_name,
        "session_id": session_id,
        "thread_id": session_id,
        "ls_model_name": model,
        "ls_temperature": temperature,
    }
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        tags=tags,
        metadata=metadata,
    )


def _configure_otlp_tracing() -> None:
    """Initialise a tracer provider that exports to the configured OTLP endpoint."""
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return
    provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


def _trace_attributes_for_root(state: PlannerState) -> Dict[str, str]:
    """Attributes attached to the root GenAI span."""
    provider_name = "openai"
    server_address = os.getenv("OPENAI_BASE_URL", "api.openai.com")
    return {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.provider.name": provider_name,
        "gen_ai.request.model": _model_name(),
        "gen_ai.agent.name": "travel_multi_agent_planner",
        "gen_ai.agent.id": f"travel_planner_{state['session_id']}",
        "gen_ai.conversation.id": state["session_id"],
        "gen_ai.request.temperature": 0.4,
        "gen_ai.request.top_p": 1.0,
        "gen_ai.request.max_tokens": 1024,
        "gen_ai.request.frequency_penalty": 0.0,
        "gen_ai.request.presence_penalty": 0.0,
        "server.address": server_address.replace("https://", "")
        .replace("http://", "")
        .rstrip("/"),
        "server.port": "443",
        "service.name": os.getenv(
            "OTEL_SERVICE_NAME",
            "opentelemetry-python-langchain-multi-agent",
        ),
    }


# ---------------------------------------------------------------------------
# LangGraph nodes
# ---------------------------------------------------------------------------


def coordinator_node(state: PlannerState) -> PlannerState:
    llm = _create_llm(
        "coordinator", temperature=0.2, session_id=state["session_id"]
    )
    system_message = SystemMessage(
        content=(
            "You are the lead travel coordinator. Extract the key details from the "
            "traveller's request and describe the plan for the specialist agents."
        )
    )
    response = llm.invoke([system_message] + state["messages"])

    state["messages"].append(response)
    state["current_agent"] = "flight_specialist"
    return state


def flight_specialist_node(state: PlannerState) -> PlannerState:
    llm = _create_llm(
        "flight_specialist", temperature=0.4, session_id=state["session_id"]
    )
    agent = _create_react_agent(llm, tools=[mock_search_flights])
    task = (
        f"Find an appealing flight from {state['origin']} to {state['destination']} "
        f"departing {state['departure']} for {state['travellers']} travellers."
    )
    result = agent.invoke({"messages": [HumanMessage(content=task)]})
    final_message = result["messages"][-1]
    state["flight_summary"] = (
        final_message.content
        if isinstance(final_message, BaseMessage)
        else str(final_message)
    )
    state["messages"].append(
        final_message
        if isinstance(final_message, BaseMessage)
        else AIMessage(content=str(final_message))
    )
    state["current_agent"] = "hotel_specialist"
    return state


def hotel_specialist_node(state: PlannerState) -> PlannerState:
    llm = _create_llm(
        "hotel_specialist", temperature=0.5, session_id=state["session_id"]
    )
    agent = _create_react_agent(llm, tools=[mock_search_hotels])
    task = (
        f"Recommend a boutique hotel in {state['destination']} between {state['departure']} "
        f"and {state['return_date']} for {state['travellers']} travellers."
    )
    result = agent.invoke({"messages": [HumanMessage(content=task)]})
    final_message = result["messages"][-1]
    state["hotel_summary"] = (
        final_message.content
        if isinstance(final_message, BaseMessage)
        else str(final_message)
    )
    state["messages"].append(
        final_message
        if isinstance(final_message, BaseMessage)
        else AIMessage(content=str(final_message))
    )
    state["current_agent"] = "activity_specialist"
    return state


def activity_specialist_node(state: PlannerState) -> PlannerState:
    llm = _create_llm(
        "activity_specialist", temperature=0.6, session_id=state["session_id"]
    )
    agent = _create_react_agent(llm, tools=[mock_search_activities])
    task = f"Curate signature activities for travellers spending a week in {state['destination']}."
    result = agent.invoke({"messages": [HumanMessage(content=task)]})
    final_message = result["messages"][-1]
    state["activities_summary"] = (
        final_message.content
        if isinstance(final_message, BaseMessage)
        else str(final_message)
    )
    state["messages"].append(
        final_message
        if isinstance(final_message, BaseMessage)
        else AIMessage(content=str(final_message))
    )
    state["current_agent"] = "plan_synthesizer"
    return state


def plan_synthesizer_node(state: PlannerState) -> PlannerState:
    llm = _create_llm(
        "plan_synthesizer", temperature=0.3, session_id=state["session_id"]
    )
    system_prompt = SystemMessage(
        content=(
            "You are the travel plan synthesiser. Combine the specialist insights into a "
            "concise, structured itinerary covering flights, accommodation and activities."
        )
    )
    content = json.dumps(
        {
            "flight": state["flight_summary"],
            "hotel": state["hotel_summary"],
            "activities": state["activities_summary"],
        },
        indent=2,
    )
    response = llm.invoke(
        [
            system_prompt,
            HumanMessage(
                content=(
                    f"Traveller request: {state['user_request']}\n\n"
                    f"Origin: {state['origin']} | Destination: {state['destination']}\n"
                    f"Dates: {state['departure']} to {state['return_date']}\n\n"
                    f"Specialist summaries:\n{content}"
                )
            ),
        ]
    )
    state["final_itinerary"] = response.content
    state["messages"].append(response)
    state["current_agent"] = "completed"
    return state


def should_continue(state: PlannerState) -> str:
    mapping = {
        "start": "coordinator",
        "flight_specialist": "flight_specialist",
        "hotel_specialist": "hotel_specialist",
        "activity_specialist": "activity_specialist",
        "plan_synthesizer": "plan_synthesizer",
    }
    return mapping.get(state["current_agent"], END)


def build_workflow() -> StateGraph:
    graph = StateGraph(PlannerState)
    graph.add_node("coordinator", coordinator_node)
    graph.add_node("flight_specialist", flight_specialist_node)
    graph.add_node("hotel_specialist", hotel_specialist_node)
    graph.add_node("activity_specialist", activity_specialist_node)
    graph.add_node("plan_synthesizer", plan_synthesizer_node)
    graph.add_conditional_edges(START, should_continue)
    graph.add_conditional_edges("coordinator", should_continue)
    graph.add_conditional_edges("flight_specialist", should_continue)
    graph.add_conditional_edges("hotel_specialist", should_continue)
    graph.add_conditional_edges("activity_specialist", should_continue)
    graph.add_conditional_edges("plan_synthesizer", should_continue)
    return graph


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    _configure_otlp_tracing()
    LangChainInstrumentor().instrument()

    session_id = str(uuid4())
    user_request = (
        "We're planning a romantic long-week trip to Paris from Seattle next month. "
        "We'd love a boutique hotel, business-class flights and a few unique experiences."
    )

    origin = _pick_origin(user_request)
    destination = _pick_destination(user_request)
    departure, return_date = _compute_dates()

    initial_state: PlannerState = {
        "messages": [HumanMessage(content=user_request)],
        "user_request": user_request,
        "session_id": session_id,
        "origin": origin,
        "destination": destination,
        "departure": departure,
        "return_date": return_date,
        "travellers": 2,
        "flight_summary": None,
        "hotel_summary": None,
        "activities_summary": None,
        "final_itinerary": None,
        "current_agent": "start",
    }

    workflow = build_workflow()
    app = workflow.compile()

    tracer = trace.get_tracer(__name__)
    attributes = _trace_attributes_for_root(initial_state)
    root_input = [
        {
            "role": "user",
            "parts": [
                {
                    "type": "text",
                    "content": user_request,
                }
            ],
        }
    ]

    with tracer.start_as_current_span(
        name="invoke_agent travel_multi_agent_planner",
        kind=SpanKind.CLIENT,
        attributes=attributes,
    ) as root_span:
        root_span.set_attribute(
            "gen_ai.input.messages", json.dumps(root_input)
        )

        config = {
            "configurable": {"thread_id": session_id},
            "recursion_limit": 10,
        }

        print("🌍 Multi-Agent Travel Planner")
        print("=" * 60)

        final_state: Optional[PlannerState] = None

        for step in app.stream(initial_state, config):
            node_name, node_state = next(iter(step.items()))
            final_state = node_state
            print(f"\n🤖 {node_name.replace('_', ' ').title()} Agent")
            if node_state.get("messages"):
                last = node_state["messages"][-1]
                if isinstance(last, BaseMessage):
                    preview = last.content
                    if len(preview) > 400:
                        preview = preview[:400] + "... [truncated]"
                    print(preview)

        if not final_state:
            final_plan = ""
        else:
            final_plan = final_state.get("final_itinerary") or ""

        if final_plan:
            print("\n🎉 Final itinerary\n" + "-" * 40)
            print(final_plan)

        root_span.set_attribute("gen_ai.response.model", _model_name())
        if final_plan:
            root_span.set_attribute(
                "gen_ai.output.messages",
                json.dumps(
                    [
                        {
                            "role": "assistant",
                            "parts": [
                                {"type": "text", "content": final_plan[:4000]}
                            ],
                            "finish_reason": "stop",
                        }
                    ]
                ),
            )
            preview = final_plan[:500] + (
                "..." if len(final_plan) > 500 else ""
            )
            root_span.set_attribute("metadata.final_plan.preview", preview)
        root_span.set_attribute("metadata.session_id", session_id)
        root_span.set_attribute(
            "metadata.agents_used",
            len(
                [
                    key
                    for key in [
                        "flight_summary",
                        "hotel_summary",
                        "activities_summary",
                    ]
                    if final_state and final_state.get(key)
                ]
            ),
        )

    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush()
    if hasattr(provider, "shutdown"):
        provider.shutdown()


if __name__ == "__main__":
    main()
