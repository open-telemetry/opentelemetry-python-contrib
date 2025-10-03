"""Enhanced Multi-Agent Travel Planning System using OpenAI Agents with OpenTelemetry instrumentation."""

import asyncio
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Azure Monitor exporter removed for this sample
from agents import (
    Agent,
    HandoffInputData,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
    handoff,
)
from agents import (
    trace as agents_trace,
)
from agents.extensions import handoff_filters
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI, AsyncOpenAI
from pydantic import BaseModel, Field

from opentelemetry import trace
from opentelemetry.instrumentation.openai_agents import (
    OpenAIAgentsInstrumentor,
)
from opentelemetry.instrumentation.openai_agents.genai_semantic_processor import (
    GenAISemanticProcessor,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

TRACER = trace.get_tracer(__name__)

# Agent metadata constants
AGENT_VERSION = "1.0.0"
AGENT_SYSTEM_ID = "travel-planner-system"
AGENT_SYSTEM_NAME = "Enhanced Travel Planning System"


class TripDetails(BaseModel):
    destination: str
    origin: str
    departure_date: str
    return_date: str
    travelers: int = Field(default=2, gt=0)
    trip_type: str = Field(default="leisure")
    budget: Optional[float] = None
    preferences: List[str] = Field(default_factory=list)


class FlightRecommendation(BaseModel):
    airline: str
    flight_number: str
    departure_time: str
    arrival_time: str
    price: float
    duration: str


class HotelRecommendation(BaseModel):
    name: str
    rating: float
    price_per_night: float
    location: str
    amenities: List[str]


class ActivityRecommendation(BaseModel):
    name: str
    category: str
    duration: str
    price: float
    description: str


class BudgetAnalysis(BaseModel):
    total_cost: float
    per_person_cost: float
    flight_cost: float
    hotel_cost: float
    activity_cost: float
    meals_cost: float
    miscellaneous: float
    budget_category: str


class CompleteTravelPlan(BaseModel):
    trip_summary: str
    flights: List[FlightRecommendation]
    hotels: List[HotelRecommendation]
    activities: List[ActivityRecommendation]
    budget: BudgetAnalysis
    day_by_day_itinerary: Dict[str, List[str]]
    important_notes: List[str]


def _configure_otel(session_id: str) -> GenAISemanticProcessor:
    """Configure OpenTelemetry with GenAI semantic processor."""
    resource = Resource.create(
        {
            "service.name": "openai-agents-enhanced-travel-planner",
            "service.version": AGENT_VERSION,
            "deployment.environment": os.getenv(
                "DEPLOYMENT_ENV", "development"
            ),
            "service.instance.id": session_id,
            "service.namespace": "travel-planning",
        }
    )

    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(tp)

    tracer = trace.get_tracer(
        "openai-agents-enhanced-travel-planner",
        AGENT_VERSION,
        schema_url="https://opentelemetry.io/schemas/1.27.0",
    )

    provider = "openai"
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    if endpoint:
        provider = "azure.ai.inference"
        base_url = endpoint.rstrip("/")
        for suffix in ("/openai", "/openai/v1", "/openai/v1/"):
            if base_url.endswith(suffix):
                base_url = base_url[: -len(suffix)]
                break

    # Enhanced agent metadata with session-specific ID
    agent_id = f"{AGENT_SYSTEM_ID}-{session_id[:8]}"

    genai_processor = GenAISemanticProcessor(
        tracer=tracer,
        event_logger=None,
        system_name=provider,
        include_sensitive_data=True,
        base_url=base_url,
        emit_legacy=False,
        agent_name=AGENT_SYSTEM_NAME,
        agent_id=agent_id,
        agent_description=(
            "Multi-agent travel planning system with specialized agents: "
            "Coordinator, Flight Specialist, Hotel Specialist, Activity Specialist, Budget Analyst, and Plan Synthesizer"
        ),
        server_address=None,
        server_port=None,
    )

    return genai_processor


def _build_async_client() -> AsyncOpenAI:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    public_key = os.getenv("OPENAI_API_KEY")

    if endpoint and key:
        endpoint = endpoint.rstrip("/")
        for suffix in ("/openai", "/openai/v1", "/openai/v1/"):
            if endpoint.endswith(suffix):
                endpoint = endpoint[: -len(suffix)]
                break
        return AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=key,
            api_version=api_version,
        )
    elif public_key:
        return AsyncOpenAI(api_key=public_key)
    else:
        raise SystemExit(
            "Set AZURE_OPENAI_* or OPENAI_API_KEY environment variables"
        )


def _build_model(
    client: AsyncOpenAI, temperature: float = 0.7
) -> OpenAIChatCompletionsModel:
    model_name = (
        os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or os.getenv("OPENAI_MODEL")
        or "gpt-4o-mini"
    )
    return OpenAIChatCompletionsModel(
        model=model_name,
        openai_client=client,
    )


def _http_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


@function_tool
async def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    travelers: int = 2,
) -> str:
    flights_data = {
        ("Seattle", "London"): [
            {
                "airline": "British Airways",
                "flight": "BA048",
                "dep": "13:25",
                "arr": "06:50+1",
                "price": 875,
            },
            {
                "airline": "Delta",
                "flight": "DL030",
                "dep": "15:45",
                "arr": "09:10+1",
                "price": 925,
            },
            {
                "airline": "Virgin Atlantic",
                "flight": "VS105",
                "dep": "09:30",
                "arr": "03:00+1",
                "price": 810,
            },
        ],
        ("Seattle", "Paris"): [
            {
                "airline": "Air France",
                "flight": "AF367",
                "dep": "12:40",
                "arr": "07:55+1",
                "price": 895,
            },
            {
                "airline": "Delta",
                "flight": "DL166",
                "dep": "14:20",
                "arr": "09:35+1",
                "price": 945,
            },
        ],
        ("Seattle", "Tokyo"): [
            {
                "airline": "ANA",
                "flight": "NH177",
                "dep": "13:20",
                "arr": "16:25+1",
                "price": 1250,
            },
            {
                "airline": "Delta",
                "flight": "DL167",
                "dep": "12:49",
                "arr": "15:55+1",
                "price": 1320,
            },
        ],
    }

    key = (origin, destination)
    flights = flights_data.get(
        key,
        [
            {
                "airline": "Generic Air",
                "flight": "GA001",
                "dep": "10:00",
                "arr": "22:00",
                "price": 750,
            }
        ],
    )

    result = f"✈️ Found {len(flights)} round-trip flights from {origin} to {destination}:\n\n"
    for i, flight in enumerate(flights, 1):
        total_price = flight["price"] * travelers * 2
        result += f"{i}. {flight['airline']} {flight['flight']}\n"
        result += f"   Outbound {departure_date}: Depart {flight['dep']} → Arrive {flight['arr']}\n"
        result += f"   Return {return_date}: Similar times\n"
        result += f"   Price: ${total_price:,} total for {travelers} travelers (round-trip)\n\n"

    return result


@function_tool
async def search_hotels(
    destination: str, check_in: str, check_out: str, travelers: int = 2
) -> str:
    hotels_data = {
        "London": [
            {
                "name": "The Langham",
                "rating": 5,
                "price": 450,
                "location": "Regent Street",
                "amenities": [
                    "Spa",
                    "Fitness Center",
                    "Restaurant",
                    "Business Center",
                    "Concierge",
                ],
            },
            {
                "name": "Premier Inn London County Hall",
                "rating": 4,
                "price": 155,
                "location": "Westminster",
                "amenities": [
                    "WiFi",
                    "Restaurant",
                    "24-hour Reception",
                    "Air Conditioning",
                ],
            },
            {
                "name": "The Zetter Townhouse",
                "rating": 4.5,
                "price": 285,
                "location": "Marylebone",
                "amenities": [
                    "Boutique",
                    "Bar",
                    "WiFi",
                    "Room Service",
                    "Unique Decor",
                ],
            },
        ],
        "Paris": [
            {
                "name": "Hôtel Plaza Athénée",
                "rating": 5,
                "price": 850,
                "location": "Avenue Montaigne",
                "amenities": [
                    "Michelin Restaurant",
                    "Spa",
                    "Designer Rooms",
                    "Eiffel Tower View",
                ],
            },
            {
                "name": "Hotel Malte Opera",
                "rating": 4,
                "price": 220,
                "location": "Opera District",
                "amenities": [
                    "Central Location",
                    "WiFi",
                    "Breakfast",
                    "Concierge",
                ],
            },
        ],
        "Tokyo": [
            {
                "name": "Park Hyatt Tokyo",
                "rating": 5,
                "price": 680,
                "location": "Shinjuku",
                "amenities": [
                    "City Views",
                    "Pool",
                    "Spa",
                    "Multiple Restaurants",
                    "Gym",
                ],
            },
            {
                "name": "Hotel Gracery Shinjuku",
                "rating": 4,
                "price": 180,
                "location": "Shinjuku",
                "amenities": [
                    "Godzilla View",
                    "Restaurant",
                    "WiFi",
                    "Central Location",
                ],
            },
        ],
    }

    hotels = hotels_data.get(
        destination,
        [
            {
                "name": "Standard Hotel",
                "rating": 3.5,
                "price": 150,
                "location": "City Center",
                "amenities": ["WiFi", "Breakfast", "24-hour Reception"],
            }
        ],
    )

    from datetime import datetime

    nights = (
        datetime.fromisoformat(check_out) - datetime.fromisoformat(check_in)
    ).days

    result = f"🏨 Found {len(hotels)} hotels in {destination} for {nights} nights:\n\n"
    for i, hotel in enumerate(hotels, 1):
        total_price = (
            hotel["price"] * nights * (travelers // 2 + travelers % 2)
        )
        result += f"{i}. {hotel['name']} ({hotel['rating']}⭐)\n"
        result += f"   Location: {hotel['location']}\n"
        result += (
            f"   Price: ${hotel['price']}/night (${total_price:,} total)\n"
        )
        result += f"   Amenities: {', '.join(hotel['amenities'][:3])}\n\n"

    return result


@function_tool
async def search_activities(
    destination: str, trip_type: str = "leisure"
) -> str:
    activities_data = {
        "London": [
            {
                "name": "British Museum Tour",
                "category": "Cultural",
                "duration": "3 hours",
                "price": 0,
            },
            {
                "name": "Tower of London",
                "category": "Historical",
                "duration": "2-3 hours",
                "price": 35,
            },
            {
                "name": "West End Theater Show",
                "category": "Entertainment",
                "duration": "2.5 hours",
                "price": 85,
            },
            {
                "name": "Thames River Cruise",
                "category": "Sightseeing",
                "duration": "1 hour",
                "price": 25,
            },
            {
                "name": "Harry Potter Studio Tour",
                "category": "Entertainment",
                "duration": "4 hours",
                "price": 55,
            },
        ],
        "Paris": [
            {
                "name": "Louvre Museum",
                "category": "Cultural",
                "duration": "3-4 hours",
                "price": 20,
            },
            {
                "name": "Eiffel Tower Summit",
                "category": "Sightseeing",
                "duration": "2 hours",
                "price": 35,
            },
            {
                "name": "Seine River Dinner Cruise",
                "category": "Dining",
                "duration": "2 hours",
                "price": 120,
            },
            {
                "name": "Versailles Day Trip",
                "category": "Historical",
                "duration": "Full day",
                "price": 45,
            },
        ],
        "Tokyo": [
            {
                "name": "Senso-ji Temple",
                "category": "Cultural",
                "duration": "2 hours",
                "price": 0,
            },
            {
                "name": "Robot Restaurant Show",
                "category": "Entertainment",
                "duration": "2 hours",
                "price": 95,
            },
            {
                "name": "Mt. Fuji Day Trip",
                "category": "Nature",
                "duration": "Full day",
                "price": 150,
            },
            {
                "name": "Sushi Making Class",
                "category": "Culinary",
                "duration": "3 hours",
                "price": 85,
            },
        ],
    }

    activities = activities_data.get(
        destination,
        [
            {
                "name": "City Walking Tour",
                "category": "Sightseeing",
                "duration": "2 hours",
                "price": 30,
            }
        ],
    )

    if trip_type == "business":
        activities = [
            a
            for a in activities
            if a["category"] in ["Dining", "Entertainment"]
        ][:3]
    elif trip_type == "family":
        activities = [a for a in activities if a["price"] < 100][:4]
    elif trip_type == "romantic":
        activities = [
            a
            for a in activities
            if a["category"] in ["Dining", "Sightseeing", "Entertainment"]
        ][:3]

    result = f"🎯 Top activities in {destination} for {trip_type} travel:\n\n"
    for i, activity in enumerate(activities, 1):
        result += f"{i}. {activity['name']}\n"
        result += f"   Category: {activity['category']} | Duration: {activity['duration']}\n"
        result += f"   Price: ${activity['price']} per person\n\n"

    return result


@function_tool
async def get_weather_forecast(destination: str, date: str) -> str:
    weather_patterns = {
        "London": {
            "temp_high": 18,
            "temp_low": 11,
            "condition": "Partly cloudy",
            "rain_chance": 40,
        },
        "Paris": {
            "temp_high": 22,
            "temp_low": 14,
            "condition": "Sunny",
            "rain_chance": 20,
        },
        "Tokyo": {
            "temp_high": 26,
            "temp_low": 19,
            "condition": "Clear",
            "rain_chance": 10,
        },
    }

    weather = weather_patterns.get(
        destination,
        {
            "temp_high": 20,
            "temp_low": 12,
            "condition": "Variable",
            "rain_chance": 30,
        },
    )

    result = f"🌤️ Weather forecast for {destination} around {date}:\n"
    result += (
        f"High: {weather['temp_high']}°C / Low: {weather['temp_low']}°C\n"
    )
    result += f"Conditions: {weather['condition']}\n"
    result += f"Chance of rain: {weather['rain_chance']}%"

    return result


@function_tool
async def analyze_trip_budget(
    flight_cost: float,
    hotel_cost: float,
    activity_costs: List[float],
    travelers: int,
    nights: int,
) -> str:
    total_activities = sum(activity_costs) * travelers
    meal_cost_per_day = 60
    total_meals = meal_cost_per_day * nights * travelers
    subtotal = flight_cost + hotel_cost + total_activities + total_meals
    miscellaneous = subtotal * 0.15
    grand_total = subtotal + miscellaneous
    per_person = grand_total / travelers

    if per_person < 1500:
        category = "Budget-Friendly"
        emoji = "💰"
    elif per_person < 2500:
        category = "Moderate"
        emoji = "💵"
    elif per_person < 4000:
        category = "Premium"
        emoji = "💎"
    else:
        category = "Luxury"
        emoji = "👑"

    result = f"{emoji} Trip Budget Analysis - {category}\n"
    result += "=" * 40 + "\n"
    result += f"✈️  Flights: ${flight_cost:,.2f}\n"
    result += f"🏨 Hotels ({nights} nights): ${hotel_cost:,.2f}\n"
    result += f"🎯 Activities: ${total_activities:,.2f}\n"
    result += f"🍽️  Meals: ${total_meals:,.2f}\n"
    result += f"💼 Miscellaneous: ${miscellaneous:,.2f}\n"
    result += "=" * 40 + "\n"
    result += f"💵 Total: ${grand_total:,.2f}\n"
    result += f"👤 Per Person: ${per_person:,.2f}\n"

    return result


def create_coordinator_agent(
    model: OpenAIChatCompletionsModel, session_id: str
) -> Agent:
    agent = Agent(
        name="Travel Coordinator",
        instructions="""Extract trip details (destination, dates, travelers, budget, preferences) and hand off to Flight Specialist.""",
        model=model,
        output_type=TripDetails,
    )
    # Add metadata as custom attributes
    agent.agent_id = f"coordinator-{session_id[:8]}"
    agent.agent_version = AGENT_VERSION
    return agent


def create_flight_specialist_agent(
    model: OpenAIChatCompletionsModel, session_id: str
) -> Agent:
    agent = Agent(
        name="Flight Specialist",
        handoff_description="Hand off to Flight Specialist to search for flights",
        instructions="""Search for optimal flights and check weather. Hand off to Hotel Specialist.""",
        model=model,
        tools=[search_flights, get_weather_forecast],
    )
    agent.agent_id = f"flight-specialist-{session_id[:8]}"
    agent.agent_version = AGENT_VERSION
    return agent


def create_hotel_specialist_agent(
    model: OpenAIChatCompletionsModel, session_id: str
) -> Agent:
    agent = Agent(
        name="Hotel Specialist",
        handoff_description="Hand off to Hotel Specialist to find accommodations",
        instructions="""Search for suitable hotels. Hand off to Activity Specialist.""",
        model=model,
        tools=[search_hotels],
    )
    agent.agent_id = f"hotel-specialist-{session_id[:8]}"
    agent.agent_version = AGENT_VERSION
    return agent


def create_activity_specialist_agent(
    model: OpenAIChatCompletionsModel, session_id: str
) -> Agent:
    agent = Agent(
        name="Activity Specialist",
        handoff_description="Hand off to Activity Specialist to plan activities",
        instructions="""Research activities and attractions. Hand off to Budget Analyst.""",
        model=model,
        tools=[search_activities, get_weather_forecast],
    )
    agent.agent_id = f"activity-specialist-{session_id[:8]}"
    agent.agent_version = AGENT_VERSION
    return agent


def create_budget_analyst_agent(
    model: OpenAIChatCompletionsModel, session_id: str
) -> Agent:
    agent = Agent(
        name="Budget Analyst",
        handoff_description="Hand off to Budget Analyst for cost analysis",
        instructions="""Calculate total trip costs. Hand off to Plan Synthesizer.""",
        model=model,
        tools=[analyze_trip_budget],
    )
    agent.agent_id = f"budget-analyst-{session_id[:8]}"
    agent.agent_version = AGENT_VERSION
    return agent


def create_plan_synthesizer_agent(
    model: OpenAIChatCompletionsModel, session_id: str
) -> Agent:
    agent = Agent(
        name="Plan Synthesizer",
        handoff_description="Hand off to Plan Synthesizer to create final plan",
        instructions="""Create comprehensive travel plan with summary, flights, hotels, activities, budget, and itinerary.""",
        model=model,
        output_type=str,
    )
    agent.agent_id = f"plan-synthesizer-{session_id[:8]}"
    agent.agent_version = AGENT_VERSION
    return agent


def create_handoff_chain(agents: Dict[str, Agent]) -> None:
    def preserve_trip_details(
        handoff_data: HandoffInputData,
    ) -> HandoffInputData:
        return handoff_data

    def summarize_for_budget(
        handoff_data: HandoffInputData,
    ) -> HandoffInputData:
        return handoff_filters.remove_all_tools(handoff_data)

    agents["coordinator"].handoffs = [
        handoff(
            agents["flight_specialist"], input_filter=preserve_trip_details
        )
    ]
    agents["flight_specialist"].handoffs = [
        handoff(agents["hotel_specialist"], input_filter=preserve_trip_details)
    ]
    agents["hotel_specialist"].handoffs = [
        handoff(
            agents["activity_specialist"], input_filter=preserve_trip_details
        )
    ]
    agents["activity_specialist"].handoffs = [
        handoff(agents["budget_analyst"], input_filter=summarize_for_budget)
    ]
    agents["budget_analyst"].handoffs = [
        handoff(agents["plan_synthesizer"], input_filter=preserve_trip_details)
    ]


async def run_travel_planning(user_request: str) -> str:
    session_id = str(uuid4())

    # Configure OpenTelemetry with session-specific ID
    genai_processor = _configure_otel(session_id)

    # Set additional context via environment variables for this session
    os.environ["OTEL_GENAI_CONVERSATION_ID"] = session_id
    os.environ["OTEL_GENAI_SESSION_ID"] = session_id

    # Instrument with the GenAI processor
    OpenAIAgentsInstrumentor().instrument(trace_processor=genai_processor)

    client = _build_async_client()

    # Create agents with session-specific IDs
    agents = {
        "coordinator": create_coordinator_agent(
            _build_model(client, temperature=0.3), session_id
        ),
        "flight_specialist": create_flight_specialist_agent(
            _build_model(client, temperature=0.5), session_id
        ),
        "hotel_specialist": create_hotel_specialist_agent(
            _build_model(client, temperature=0.5), session_id
        ),
        "activity_specialist": create_activity_specialist_agent(
            _build_model(client, temperature=0.7), session_id
        ),
        "budget_analyst": create_budget_analyst_agent(
            _build_model(client, temperature=0.3), session_id
        ),
        "plan_synthesizer": create_plan_synthesizer_agent(
            _build_model(client, temperature=0.5), session_id
        ),
    }

    create_handoff_chain(agents)

    with agents_trace(workflow_name=f"travel_planning_{session_id}"):
        # Add span attributes for the workflow
        with TRACER.start_as_current_span("travel_planning_workflow") as span:
            span.set_attribute("workflow.session_id", session_id)
            span.set_attribute("workflow.agent_count", len(agents))
            span.set_attribute(
                "workflow.user_request", user_request[:200]
            )  # Truncate for privacy

            coordinator_result = await Runner.run(
                agents["coordinator"], user_request
            )
            raw_trip_details = coordinator_result.final_output

            trip_details: Optional[TripDetails] = None
            if isinstance(raw_trip_details, TripDetails):
                trip_details = raw_trip_details
            else:
                parsed: Optional[Dict[str, Any]] = None
                if isinstance(raw_trip_details, dict):
                    parsed = raw_trip_details
                elif isinstance(raw_trip_details, str):
                    try:
                        parsed = json.loads(raw_trip_details)
                    except Exception:
                        import re

                        text = raw_trip_details

                        def _match(pattern: str) -> Optional[str]:
                            match = re.search(
                                pattern, text, flags=re.IGNORECASE
                            )
                            if match:
                                return match.group(1).strip()
                            return None

                        origin = _match(
                            r"from\s+([A-Za-z\s]+?)(?:\s+to|\.|,|\n)"
                        )
                        destination = _match(r"to\s+([A-Za-z\s]+?)(?:\.|,|\n)")
                        dep = _match(
                            r"depart?(?:\s+date)?[:\-]?\s*(\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{1,2})"
                        )
                        ret = _match(
                            r"return(?:\s+date)?[:\-]?\s*(\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{1,2})"
                        )
                        travelers = _match(
                            r"(\d+)\s+(?:traveler|people|persons|adults|guests)"
                        )
                        trip_type = _match(
                            r"(business|leisure|family|romantic|adventure|cultural)"
                        )
                        budget = _match(r"\$?([0-9]{3,6})")

                        def _normalize_date(
                            val: Optional[str],
                        ) -> Optional[str]:
                            if not val:
                                return None
                            if re.match(r"\d{4}-\d{2}-\d{2}", val):
                                return val
                            try:
                                dt = datetime.strptime(
                                    val + " " + str(datetime.now().year),
                                    "%B %d %Y",
                                )
                                return dt.date().isoformat()
                            except Exception:
                                return None

                        parsed = {}
                        if origin:
                            parsed["origin"] = origin.title()
                        if destination:
                            parsed["destination"] = destination.title()
                        if dep:
                            parsed["departure_date"] = (
                                _normalize_date(dep) or dep
                            )
                        if ret:
                            parsed["return_date"] = _normalize_date(ret) or ret
                        if travelers:
                            parsed["travelers"] = int(travelers)
                        if trip_type:
                            parsed["trip_type"] = trip_type.lower()
                        if budget:
                            parsed["budget"] = float(budget)
                        required = {
                            "origin",
                            "destination",
                            "departure_date",
                            "return_date",
                        }
                        if not required.issubset(parsed.keys()):
                            parsed = None

                if parsed:
                    try:
                        trip_details = TripDetails.model_validate(parsed)
                    except Exception:
                        trip_details = None

            if not trip_details:
                raise ValueError(
                    f"Failed to extract trip details from: {raw_trip_details}"
                )

            # Add trip details to span
            span.set_attribute("trip.destination", trip_details.destination)
            span.set_attribute("trip.origin", trip_details.origin)
            span.set_attribute("trip.travelers", trip_details.travelers)
            span.set_attribute("trip.type", trip_details.trip_type)

            flight_prompt = f"""Find flights:
            From: {trip_details.origin} To: {trip_details.destination}
            Departure: {trip_details.departure_date} Return: {trip_details.return_date}
            Travelers: {trip_details.travelers}"""

            flight_result = await Runner.run(
                agents["flight_specialist"],
                coordinator_result.to_input_list()
                + [{"content": flight_prompt, "role": "user"}],
            )

            hotel_prompt = f"""Find hotels:
            Destination: {trip_details.destination}
            Check-in: {trip_details.departure_date} Check-out: {trip_details.return_date}
            Travelers: {trip_details.travelers} Type: {trip_details.trip_type}"""

            hotel_result = await Runner.run(
                agents["hotel_specialist"],
                flight_result.to_input_list()
                + [{"content": hotel_prompt, "role": "user"}],
            )

            prefs = (
                ", ".join(trip_details.preferences)
                if trip_details.preferences
                else "General"
            )
            activity_prompt = f"""Plan activities:
            Destination: {trip_details.destination} Type: {trip_details.trip_type}
            Preferences: {prefs} Duration: {trip_details.departure_date} to {trip_details.return_date}"""

            activity_result = await Runner.run(
                agents["activity_specialist"],
                hotel_result.to_input_list()
                + [{"content": activity_prompt, "role": "user"}],
            )

            dep_date = datetime.fromisoformat(trip_details.departure_date)
            ret_date = datetime.fromisoformat(trip_details.return_date)
            nights = (ret_date - dep_date).days

            budget_prompt = f"""Analyze budget:
            Review flight, hotel, and activity costs above.
            Travelers: {trip_details.travelers} Nights: {nights}"""

            budget_result = await Runner.run(
                agents["budget_analyst"],
                activity_result.to_input_list()
                + [{"content": budget_prompt, "role": "user"}],
            )

            synthesis_prompt = f"""Create comprehensive travel plan from all findings.
            Original request: {user_request}
            Include: summary, flights, hotels, itinerary, budget, tips."""

            final_result = await Runner.run(
                agents["plan_synthesizer"],
                budget_result.to_input_list()
                + [{"content": synthesis_prompt, "role": "user"}],
            )

            span.set_attribute("workflow.status", "completed")

    return final_result.final_output


SAMPLE_REQUESTS = {
    "business": "Business trip to London for 3 days from Seattle. Near financial district, efficient flights. Budget $3000.",
    "family": "Family vacation to Paris for 2 adults and 2 children for 10 days next month. Museums, parks. Budget $8000.",
    "romantic": "Romantic anniversary trip to Tokyo for 2 for a week. Luxury accommodations, fine dining. Budget $6000.",
}


async def main():
    load_dotenv()

    if not (os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        print("Set AZURE_OPENAI_* or OPENAI_API_KEY environment variables")
        return

    user_input = input(
        "Describe your travel plans (or press Enter for sample): "
    ).strip()

    if not user_input:
        user_input = SAMPLE_REQUESTS["business"]

    try:
        final_plan = await run_travel_planning(user_input)
        print("\n" + "=" * 70)
        print(final_plan)
        print("=" * 70)
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        try:
            trace.get_tracer_provider().force_flush()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
