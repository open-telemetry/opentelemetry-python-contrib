"""
Enhanced Multi-Agent Travel Planning System using OpenAI Agents
Replicates the LangGraph example using the agents library with proper instrumentation.
"""

import asyncio
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypedDict
from uuid import uuid4
from enum import Enum

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from openai import AsyncOpenAI, AsyncAzureOpenAI
from opentelemetry.instrumentation.openai_agents import OpenAIAgentsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry import trace

try:
    from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
except ImportError:
    AzureMonitorTraceExporter = None

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    function_tool,
    handoff,
    trace as agents_trace,
    HandoffInputData,
)
from agents.extensions import handoff_filters

# Constants
TRACER = trace.get_tracer(__name__)

# Pydantic models for structured outputs
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
    budget_category: str  # budget-friendly, moderate, premium, luxury

class CompleteTravelPlan(BaseModel):
    trip_summary: str
    flights: List[FlightRecommendation]
    hotels: List[HotelRecommendation]
    activities: List[ActivityRecommendation]
    budget: BudgetAnalysis
    day_by_day_itinerary: Dict[str, List[str]]
    important_notes: List[str]

# Configuration
def _configure_otel() -> None:
    """Configure OpenTelemetry with Azure Monitor or console export."""
    conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING") or os.getenv("APPLICATION_INSIGHTS_CONNECTION_STRING")
    resource = Resource.create({"service.name": "openai-agents-enhanced-travel-planner"})
    
    tp = TracerProvider(resource=resource)
    
    if conn and AzureMonitorTraceExporter:
        tp.add_span_processor(BatchSpanProcessor(AzureMonitorTraceExporter.from_connection_string(conn)))
        # tp.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        print("[otel] Azure Monitor trace exporter configured")
    else:
        tp.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        print("[otel] Console span exporter configured")
    
    trace.set_tracer_provider(tp)

def _build_async_client() -> AsyncOpenAI:
    """Build Azure OpenAI or OpenAI client based on environment."""
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    public_key = os.getenv("OPENAI_API_KEY")
    
    if endpoint and key:
        # Clean up Azure endpoint
        endpoint = endpoint.rstrip("/")
        for suffix in ("/openai", "/openai/v1", "/openai/v1/"):
            if endpoint.endswith(suffix):
                endpoint = endpoint[:-len(suffix)]
                break
        print(f"[config] Using Azure OpenAI: {endpoint}")
        return AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=key,
            api_version=api_version,
        )
    elif public_key:
        print("[config] Using OpenAI")
        return AsyncOpenAI(api_key=public_key)
    else:
        raise SystemExit("Set AZURE_OPENAI_* or OPENAI_API_KEY environment variables")

def _build_model(client: AsyncOpenAI, temperature: float = 0.7) -> OpenAIChatCompletionsModel:
    """Build model with appropriate deployment/model name."""
    model_name = (
        os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or os.getenv("OPENAI_MODEL")
        or "gpt-4o-mini"
    )
    print(f"[config] Using model: {model_name}")
    return OpenAIChatCompletionsModel(
        model=model_name,
        openai_client=client,
        # temperature=temperature TODO: temp not supported in all models
    )

# Shared tools for data fetching
def _http_json(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """Helper to fetch JSON from APIs."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}

@function_tool
async def search_flights(origin: str, destination: str, departure_date: str, return_date: str, travelers: int = 2) -> str:
    """Search for round-trip flights between cities."""
    # Simulated flight search with realistic data
    flights_data = {
        ("Seattle", "London"): [
            {"airline": "British Airways", "flight": "BA048", "dep": "13:25", "arr": "06:50+1", "price": 875},
            {"airline": "Delta", "flight": "DL030", "dep": "15:45", "arr": "09:10+1", "price": 925},
            {"airline": "Virgin Atlantic", "flight": "VS105", "dep": "09:30", "arr": "03:00+1", "price": 810},
        ],
        ("Seattle", "Paris"): [
            {"airline": "Air France", "flight": "AF367", "dep": "12:40", "arr": "07:55+1", "price": 895},
            {"airline": "Delta", "flight": "DL166", "dep": "14:20", "arr": "09:35+1", "price": 945},
        ],
        ("Seattle", "Tokyo"): [
            {"airline": "ANA", "flight": "NH177", "dep": "13:20", "arr": "16:25+1", "price": 1250},
            {"airline": "Delta", "flight": "DL167", "dep": "12:49", "arr": "15:55+1", "price": 1320},
        ],
    }
    
    key = (origin, destination)
    flights = flights_data.get(key, [
        {"airline": "Generic Air", "flight": "GA001", "dep": "10:00", "arr": "22:00", "price": 750}
    ])
    
    result = f"✈️ Found {len(flights)} round-trip flights from {origin} to {destination}:\n\n"
    for i, flight in enumerate(flights, 1):
        total_price = flight["price"] * travelers * 2  # Round trip
        result += f"{i}. {flight['airline']} {flight['flight']}\n"
        result += f"   Outbound {departure_date}: Depart {flight['dep']} → Arrive {flight['arr']}\n"
        result += f"   Return {return_date}: Similar times\n"
        result += f"   Price: ${total_price:,} total for {travelers} travelers (round-trip)\n\n"
    
    return result

@function_tool
async def search_hotels(destination: str, check_in: str, check_out: str, travelers: int = 2) -> str:
    """Search for hotels in destination."""
    hotels_data = {
        "London": [
            {"name": "The Langham", "rating": 5, "price": 450, "location": "Regent Street", 
             "amenities": ["Spa", "Fitness Center", "Restaurant", "Business Center", "Concierge"]},
            {"name": "Premier Inn London County Hall", "rating": 4, "price": 155, "location": "Westminster",
             "amenities": ["WiFi", "Restaurant", "24-hour Reception", "Air Conditioning"]},
            {"name": "The Zetter Townhouse", "rating": 4.5, "price": 285, "location": "Marylebone",
             "amenities": ["Boutique", "Bar", "WiFi", "Room Service", "Unique Decor"]},
        ],
        "Paris": [
            {"name": "Hôtel Plaza Athénée", "rating": 5, "price": 850, "location": "Avenue Montaigne",
             "amenities": ["Michelin Restaurant", "Spa", "Designer Rooms", "Eiffel Tower View"]},
            {"name": "Hotel Malte Opera", "rating": 4, "price": 220, "location": "Opera District",
             "amenities": ["Central Location", "WiFi", "Breakfast", "Concierge"]},
        ],
        "Tokyo": [
            {"name": "Park Hyatt Tokyo", "rating": 5, "price": 680, "location": "Shinjuku",
             "amenities": ["City Views", "Pool", "Spa", "Multiple Restaurants", "Gym"]},
            {"name": "Hotel Gracery Shinjuku", "rating": 4, "price": 180, "location": "Shinjuku",
             "amenities": ["Godzilla View", "Restaurant", "WiFi", "Central Location"]},
        ],
    }
    
    hotels = hotels_data.get(destination, [
        {"name": "Standard Hotel", "rating": 3.5, "price": 150, "location": "City Center",
         "amenities": ["WiFi", "Breakfast", "24-hour Reception"]}
    ])
    
    # Calculate nights
    from datetime import datetime
    nights = (datetime.fromisoformat(check_out) - datetime.fromisoformat(check_in)).days
    
    result = f"🏨 Found {len(hotels)} hotels in {destination} for {nights} nights:\n\n"
    for i, hotel in enumerate(hotels, 1):
        total_price = hotel["price"] * nights * (travelers // 2 + travelers % 2)  # Rooms needed
        result += f"{i}. {hotel['name']} ({hotel['rating']}⭐)\n"
        result += f"   Location: {hotel['location']}\n"
        result += f"   Price: ${hotel['price']}/night (${total_price:,} total)\n"
        result += f"   Amenities: {', '.join(hotel['amenities'][:3])}\n\n"
    
    return result

@function_tool
async def search_activities(destination: str, trip_type: str = "leisure") -> str:
    """Search for activities and attractions."""
    activities_data = {
        "London": [
            {"name": "British Museum Tour", "category": "Cultural", "duration": "3 hours", "price": 0},
            {"name": "Tower of London", "category": "Historical", "duration": "2-3 hours", "price": 35},
            {"name": "West End Theater Show", "category": "Entertainment", "duration": "2.5 hours", "price": 85},
            {"name": "Thames River Cruise", "category": "Sightseeing", "duration": "1 hour", "price": 25},
            {"name": "Harry Potter Studio Tour", "category": "Entertainment", "duration": "4 hours", "price": 55},
        ],
        "Paris": [
            {"name": "Louvre Museum", "category": "Cultural", "duration": "3-4 hours", "price": 20},
            {"name": "Eiffel Tower Summit", "category": "Sightseeing", "duration": "2 hours", "price": 35},
            {"name": "Seine River Dinner Cruise", "category": "Dining", "duration": "2 hours", "price": 120},
            {"name": "Versailles Day Trip", "category": "Historical", "duration": "Full day", "price": 45},
        ],
        "Tokyo": [
            {"name": "Senso-ji Temple", "category": "Cultural", "duration": "2 hours", "price": 0},
            {"name": "Robot Restaurant Show", "category": "Entertainment", "duration": "2 hours", "price": 95},
            {"name": "Mt. Fuji Day Trip", "category": "Nature", "duration": "Full day", "price": 150},
            {"name": "Sushi Making Class", "category": "Culinary", "duration": "3 hours", "price": 85},
        ],
    }
    
    activities = activities_data.get(destination, [
        {"name": "City Walking Tour", "category": "Sightseeing", "duration": "2 hours", "price": 30}
    ])
    
    # Filter by trip type preference
    if trip_type == "business":
        activities = [a for a in activities if a["category"] in ["Dining", "Entertainment"]][:3]
    elif trip_type == "family":
        activities = [a for a in activities if a["price"] < 100][:4]
    elif trip_type == "romantic":
        activities = [a for a in activities if a["category"] in ["Dining", "Sightseeing", "Entertainment"]][:3]
    
    result = f"🎯 Top activities in {destination} for {trip_type} travel:\n\n"
    for i, activity in enumerate(activities, 1):
        result += f"{i}. {activity['name']}\n"
        result += f"   Category: {activity['category']} | Duration: {activity['duration']}\n"
        result += f"   Price: ${activity['price']} per person\n\n"
    
    return result

@function_tool
async def get_weather_forecast(destination: str, date: str) -> str:
    """Get weather forecast for destination."""
    # Simulated weather data
    weather_patterns = {
        "London": {"temp_high": 18, "temp_low": 11, "condition": "Partly cloudy", "rain_chance": 40},
        "Paris": {"temp_high": 22, "temp_low": 14, "condition": "Sunny", "rain_chance": 20},
        "Tokyo": {"temp_high": 26, "temp_low": 19, "condition": "Clear", "rain_chance": 10},
    }
    
    weather = weather_patterns.get(destination, {
        "temp_high": 20, "temp_low": 12, "condition": "Variable", "rain_chance": 30
    })
    
    result = f"🌤️ Weather forecast for {destination} around {date}:\n"
    result += f"High: {weather['temp_high']}°C / Low: {weather['temp_low']}°C\n"
    result += f"Conditions: {weather['condition']}\n"
    result += f"Chance of rain: {weather['rain_chance']}%"
    
    return result

@function_tool
async def analyze_trip_budget(
    flight_cost: float,
    hotel_cost: float,
    activity_costs: List[float],
    travelers: int,
    nights: int
) -> str:
    """Analyze and break down trip budget."""
    # Calculate all costs
    total_activities = sum(activity_costs) * travelers
    
    # Estimate meals based on destination (per person per day)
    meal_cost_per_day = 60  # Average
    total_meals = meal_cost_per_day * nights * travelers
    
    # Miscellaneous (15% of subtotal)
    subtotal = flight_cost + hotel_cost + total_activities + total_meals
    miscellaneous = subtotal * 0.15
    
    grand_total = subtotal + miscellaneous
    per_person = grand_total / travelers
    
    # Determine budget category
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
    result += "="*40 + "\n"
    result += f"✈️  Flights: ${flight_cost:,.2f}\n"
    result += f"🏨 Hotels ({nights} nights): ${hotel_cost:,.2f}\n"
    result += f"🎯 Activities: ${total_activities:,.2f}\n"
    result += f"🍽️  Meals: ${total_meals:,.2f}\n"
    result += f"💼 Miscellaneous: ${miscellaneous:,.2f}\n"
    result += "="*40 + "\n"
    result += f"💵 Total: ${grand_total:,.2f}\n"
    result += f"👤 Per Person: ${per_person:,.2f}\n"
    
    return result

# Agent definitions with handoffs
def create_coordinator_agent(model: OpenAIChatCompletionsModel) -> Agent:
    """Create the main coordinator agent that manages the planning flow."""
    return Agent(
        name="Travel Coordinator",
        instructions="""You are the Travel Planning Coordinator. Your role is to:
        1. Understand the user's travel requirements
        2. Extract trip details (destination, dates, travelers, budget, preferences)
        3. Coordinate the planning process by handing off to specialist agents
        4. Ensure comprehensive travel planning
        
        Start by analyzing the request and extracting trip details, then hand off to the Flight Specialist.""",
        model=model,
        output_type=TripDetails,
    )

def create_flight_specialist_agent(model: OpenAIChatCompletionsModel) -> Agent:
    """Create flight booking specialist agent."""
    return Agent(
        name="Flight Specialist",
        handoff_description="Hand off to Flight Specialist to search for flights",
        instructions="""You are the Flight Specialist. Your responsibilities:
        1. Search for optimal flight options based on trip details
        2. Consider departure/return dates and number of travelers
        3. Check weather conditions for travel dates
        4. Provide detailed flight recommendations with prices
        
        After finding flights, hand off to the Hotel Specialist.""",
        model=model,
        tools=[search_flights, get_weather_forecast],
    )

def create_hotel_specialist_agent(model: OpenAIChatCompletionsModel) -> Agent:
    """Create hotel booking specialist agent."""
    return Agent(
        name="Hotel Specialist",
        handoff_description="Hand off to Hotel Specialist to find accommodations",
        instructions="""You are the Hotel Specialist. Your responsibilities:
        1. Search for suitable accommodations based on destination and dates
        2. Consider trip type (business/leisure/family/romantic) for recommendations
        3. Factor in number of travelers for room requirements
        4. Provide detailed hotel options with amenities and pricing
        
        After finding hotels, hand off to the Activity Specialist.""",
        model=model,
        tools=[search_hotels],
    )

def create_activity_specialist_agent(model: OpenAIChatCompletionsModel) -> Agent:
    """Create activity planning specialist agent."""
    return Agent(
        name="Activity Specialist",
        handoff_description="Hand off to Activity Specialist to plan activities",
        instructions="""You are the Activity Specialist. Your responsibilities:
        1. Research activities and attractions at the destination
        2. Customize recommendations based on trip type and preferences
        3. Create a balanced mix of activities
        4. Consider weather and seasonal factors
        
        After planning activities, hand off to the Budget Analyst.""",
        model=model,
        tools=[search_activities, get_weather_forecast],
    )

def create_budget_analyst_agent(model: OpenAIChatCompletionsModel) -> Agent:
    """Create budget analysis specialist agent."""
    return Agent(
        name="Budget Analyst",
        handoff_description="Hand off to Budget Analyst for cost analysis",
        instructions="""You are the Budget Analyst. Your responsibilities:
        1. Calculate total trip costs from all components
        2. Break down expenses by category
        3. Determine per-person costs
        4. Provide budget optimization suggestions
        
        After analyzing the budget, hand off to the Plan Synthesizer.""",
        model=model,
        tools=[analyze_trip_budget],
    )

def create_plan_synthesizer_agent(model: OpenAIChatCompletionsModel) -> Agent:
    """Create final plan synthesis agent."""
    return Agent(
        name="Plan Synthesizer",
        handoff_description="Hand off to Plan Synthesizer to create final plan",
        instructions="""You are the Plan Synthesizer. Create a comprehensive travel plan that includes:
        1. Executive Summary of the trip
        2. Flight details and recommendations
        3. Hotel selections with reasoning
        4. Day-by-day activity itinerary
        5. Complete budget breakdown
        6. Important travel tips and notes
        7. Emergency contacts and contingency plans
        
        Compile all specialist findings into a cohesive, actionable travel plan.""",
        model=model,
        output_type=str,
    )

def create_handoff_chain(agents: Dict[str, Agent]) -> None:
    """Set up the deterministic handoff chain between agents."""
    
    # Define handoff filters for context management
    def preserve_trip_details(handoff_data: HandoffInputData) -> HandoffInputData:
        """Preserve trip details across handoffs."""
        # Keep all history for context
        return handoff_data
    
    def summarize_for_budget(handoff_data: HandoffInputData) -> HandoffInputData:
        """Summarize findings for budget analyst."""
        # Remove tool calls but keep findings
        return handoff_filters.remove_all_tools(handoff_data)
    
    # Set up the handoff chain
    agents["coordinator"].handoffs = [
        handoff(agents["flight_specialist"], input_filter=preserve_trip_details)
    ]
    
    agents["flight_specialist"].handoffs = [
        handoff(agents["hotel_specialist"], input_filter=preserve_trip_details)
    ]
    
    agents["hotel_specialist"].handoffs = [
        handoff(agents["activity_specialist"], input_filter=preserve_trip_details)
    ]
    
    agents["activity_specialist"].handoffs = [
        handoff(agents["budget_analyst"], input_filter=summarize_for_budget)
    ]
    
    agents["budget_analyst"].handoffs = [
        handoff(agents["plan_synthesizer"], input_filter=preserve_trip_details)
    ]

async def run_travel_planning(user_request: str) -> str:
    """Execute the complete travel planning workflow."""
    
    # Initialize OpenTelemetry
    _configure_otel()
    OpenAIAgentsInstrumentor().instrument()
    
    # Create client and models with different temperatures
    client = _build_async_client()
    
    # Create all agents
    agents = {
        "coordinator": create_coordinator_agent(_build_model(client, temperature=0.3)),
        "flight_specialist": create_flight_specialist_agent(_build_model(client, temperature=0.5)),
        "hotel_specialist": create_hotel_specialist_agent(_build_model(client, temperature=0.5)),
        "activity_specialist": create_activity_specialist_agent(_build_model(client, temperature=0.7)),
        "budget_analyst": create_budget_analyst_agent(_build_model(client, temperature=0.3)),
        "plan_synthesizer": create_plan_synthesizer_agent(_build_model(client, temperature=0.5)),
    }
    
    # Set up handoff chain
    create_handoff_chain(agents)
    
    session_id = str(uuid4())
    
    # Run the deterministic workflow with tracing
    with agents_trace(workflow_name=f"travel_planning_{session_id}"):
        print(f"\n🚀 Starting Travel Planning (Session: {session_id})\n")
        print("="*70)
        
        # Step 1: Coordinator extracts trip details
        print("🤖 Travel Coordinator analyzing request...")
        coordinator_result = await Runner.run(
            agents["coordinator"],
            user_request
        )
        
        raw_trip_details = coordinator_result.final_output

    # Attempt to coerce coordinator output into TripDetails if possible.
        trip_details: Optional[TripDetails] = None
        if isinstance(raw_trip_details, TripDetails):
            trip_details = raw_trip_details
        else:
            parsed: Optional[Dict[str, Any]] = None
            if isinstance(raw_trip_details, dict):
                parsed = raw_trip_details
            elif isinstance(raw_trip_details, str):
                # Try JSON
                try:
                    parsed = json.loads(raw_trip_details)
                except Exception:
                    # Heuristic extraction
                    import re
                    text = raw_trip_details

                    def _match(pattern: str) -> Optional[str]:
                        """Return first capture group for pattern or None."""
                        match = re.search(pattern, text, flags=re.IGNORECASE)
                        if match:
                            return match.group(1).strip()
                        return None

                    origin = _match(r"from\s+([A-Za-z\s]+?)(?:\s+to|\.|,|\n)")
                    destination = _match(r"to\s+([A-Za-z\s]+?)(?:\.|,|\n)")
                    dep = _match(
                        r"depart(?:ure)?(?:\s+date)?[:\-]?\s*"
                        r"(\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{1,2})"
                    )
                    ret = _match(
                        r"return(?:\s+date)?[:\-]?\s*"
                        r"(\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{1,2})"
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
                    ) -> Optional[str]:  # noqa: D401
                        """Normalize date formats to ISO if possible."""
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
                        parsed["departure_date"] = _normalize_date(dep) or dep
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
            # Interactive fallback: collect missing fields instead of failing.
            interactive = os.getenv("INTERACTIVE_TRIP_DETAILS", "1") == "1"
            if interactive:
                print(
                    "⚠️ Coordinator did not return structured trip details. "
                    "We'll gather missing info interactively. Press Enter to "
                    "accept defaults."
                )
                # re already imported earlier

                # Try to salvage partial info from user_request / raw output
                base_text = f"{user_request}\n\n{raw_trip_details}"
                dest_match = re.search(
                    r"to\s+([A-Z][A-Za-z\-\s]{2,})", base_text, re.IGNORECASE
                )
                destination_guess = None
                if dest_match:
                    destination_guess = dest_match.group(1).strip().split()[0]

                type_match = re.search(
                    r"(business|leisure|family|romantic|adventure|cultural)",
                    base_text,
                    re.IGNORECASE,
                )
                trip_type_guess = (
                    type_match.group(1).lower() if type_match else "leisure"
                )

                budget_match = re.search(r"\$([0-9]{3,6})", base_text)
                budget_guess = (
                    float(budget_match.group(1)) if budget_match else None
                )

                # Duration detection (e.g., "5 days")
                duration_match = re.search(
                    r"(\d{1,2})\s+days?", base_text, re.IGNORECASE
                )
                duration_days = (
                    int(duration_match.group(1)) if duration_match else 5
                )

                today = datetime.now().date()
                default_departure = today + timedelta(days=30)
                default_return = default_departure + timedelta(
                    days=duration_days
                )

                def _prompt(label: str, default: Optional[str] = None) -> str:
                    prompt_text = label
                    if default:
                        prompt_text += f" [{default}]"
                    prompt_text += ": "
                    resp = input(prompt_text).strip()
                    return resp or (default or "")

                origin = _prompt("Origin city", None)
                while not origin:
                    origin = _prompt("Origin city (required)", None)

                destination = _prompt(
                    "Destination city", destination_guess or ""
                ) or destination_guess or "Unknown"

                dep_date = _prompt(
                    "Departure date (YYYY-MM-DD)",
                    default_departure.isoformat(),
                )
                ret_date = _prompt(
                    "Return date (YYYY-MM-DD)", default_return.isoformat()
                )

                travelers_raw = _prompt("Number of travelers", "2")
                try:
                    travelers_val = int(travelers_raw)
                    if travelers_val <= 0:
                        travelers_val = 2
                except Exception:
                    travelers_val = 2

                trip_type_val = _prompt(
                    "Trip type (business/leisure/family/romantic/"
                    "adventure/cultural)",
                    trip_type_guess,
                )
                if trip_type_val not in [
                    "business",
                    "leisure",
                    "family",
                    "romantic",
                    "adventure",
                    "cultural",
                ]:
                    trip_type_val = trip_type_guess

                budget_val = None
                if budget_guess:
                    budget_in = _prompt(
                        "Approximate budget (number)", str(int(budget_guess))
                    )
                else:
                    budget_in = _prompt("Approximate budget (optional)", "")
                if budget_in:
                    try:
                        budget_val = float(budget_in)
                    except Exception:
                        budget_val = budget_guess

                preferences_in = _prompt(
                    "List key preferences (comma separated)", ""
                )
                prefs_list = [
                    p.strip()
                    for p in preferences_in.split(",")
                    if p.strip()
                ]

                try:
                    trip_details = TripDetails(
                        destination=destination,
                        origin=origin,
                        departure_date=dep_date,
                        return_date=ret_date,
                        travelers=travelers_val,
                        trip_type=trip_type_val,
                        budget=budget_val,
                        preferences=prefs_list,
                    )
                except Exception as err:  # noqa: BLE001
                    raise ValueError(
                        "Failed to build TripDetails from interactive input: "
                        f"{err}"
                    ) from err
            else:
                raise ValueError(
                    "Coordinator did not return structured TripDetails. Got: "
                    f"{type(raw_trip_details).__name__}: "
                    f"{raw_trip_details!r}. "
                    "Please refine: origin, destination, ISO dates, "
                    "travelers, optional budget."
                )

        print("✅ Trip Details Extracted:")
        print(f"   📍 {trip_details.origin} → {trip_details.destination}")
        print(
            f"   📅 {trip_details.departure_date} to "
            f"{trip_details.return_date}"
        )
        print(f"   👥 {trip_details.travelers} travelers")
        print(f"   🎯 Type: {trip_details.trip_type}")
        if trip_details.budget:
            print(f"   💰 Budget: ${trip_details.budget:,.0f}")
        print()
        
        # Step 2: Flight Specialist searches flights
        print("🤖 Flight Specialist searching flights...")
        flight_prompt = f"""Find flights for this trip:
        - From: {trip_details.origin}
        - To: {trip_details.destination}
        - Departure: {trip_details.departure_date}
        - Return: {trip_details.return_date}
        - Travelers: {trip_details.travelers}
        
        Also check weather conditions for these dates."""
        
        flight_result = await Runner.run(
            agents["flight_specialist"],
            coordinator_result.to_input_list()
            + [{"content": flight_prompt, "role": "user"}],
        )
        print("✅ Flight options found\n")
        
        # Step 3: Hotel Specialist finds accommodations
        print("🤖 Hotel Specialist searching hotels...")
        hotel_prompt = f"""Find hotels for:
        - Destination: {trip_details.destination}
        - Check-in: {trip_details.departure_date}
        - Check-out: {trip_details.return_date}
        - Travelers: {trip_details.travelers}
        - Trip type: {trip_details.trip_type}"""
        
        hotel_result = await Runner.run(
            agents["hotel_specialist"],
            flight_result.to_input_list()
            + [{"content": hotel_prompt, "role": "user"}],
        )
        print("✅ Hotel options found\n")
        
        # Step 4: Activity Specialist plans activities
        print("🤖 Activity Specialist planning activities...")
        prefs = (
            ", ".join(trip_details.preferences)
            if trip_details.preferences
            else "General"
        )
        activity_prompt = (
            "Plan activities for:\n"
            f"- Destination: {trip_details.destination}\n"
            f"- Trip type: {trip_details.trip_type}\n"
            f"- Preferences: {prefs}\n"
            f"- Duration: {trip_details.departure_date} to "
            f"{trip_details.return_date}"
        )
        
        activity_result = await Runner.run(
            agents["activity_specialist"],
            hotel_result.to_input_list()
            + [{"content": activity_prompt, "role": "user"}],
        )
        print("✅ Activities planned\n")
        
        # Step 5: Budget Analyst calculates costs
        print("🤖 Budget Analyst calculating costs...")
        
        # Calculate nights
    # datetime imported at top; reuse here
        dep_date = datetime.fromisoformat(trip_details.departure_date)
        ret_date = datetime.fromisoformat(trip_details.return_date)
        nights = (ret_date - dep_date).days
        
        budget_prompt = (
            "Analyze the budget for this trip:\n"
            "- Review the flight costs mentioned above\n"
            "- Review the hotel costs mentioned above\n"
            "- Review the activity costs mentioned above\n"
            f"- Travelers: {trip_details.travelers}\n"
            f"- Nights: {nights}\n\n"
            "Provide a comprehensive budget breakdown."
        )
        
        budget_result = await Runner.run(
            agents["budget_analyst"],
            activity_result.to_input_list()
            + [{"content": budget_prompt, "role": "user"}],
        )
        print("✅ Budget analysis complete\n")
        
        # Step 6: Plan Synthesizer creates final plan
        print("🤖 Plan Synthesizer creating comprehensive plan...")
        synthesis_prompt = (
            "Create a comprehensive travel plan from all specialist "
            "findings.\n\n"
            f"Original request: {user_request}\n\n"
            "Include:\n"
            "1. Trip summary\n"
            "2. Selected flights\n"
            "3. Recommended hotels\n"
            "4. Day-by-day itinerary with activities\n"
            "5. Budget breakdown\n"
            "6. Travel tips and notes\n\n"
            "Make it detailed and actionable."
        )
        
        final_result = await Runner.run(
            agents["plan_synthesizer"],
            budget_result.to_input_list()
            + [{"content": synthesis_prompt, "role": "user"}],
        )
        
        print("✅ Travel plan complete!\n")
        print("="*70)
        
    # Extract and return the final plan
    return final_result.final_output

# Sample requests for testing
SAMPLE_REQUESTS = {
    "business": (
        "I need to plan a business trip to London for 3 days. I'm traveling "
        "from Seattle, want a hotel near the financial district, prefer "
        "efficient flights. Budget around $3000."
    ),
    "family": (
        "Plan a family vacation to Paris for 2 adults and 2 children for 10 "
        "days next month. We love museums, parks, family-friendly activities. "
        "Budget flexible, about $8000 total."
    ),
    "romantic": (
        "Plan a romantic anniversary trip to Tokyo for 2 people for a week. "
        "We want luxury accommodations, fine dining, romantic experiences. "
        "Budget up to $6000."
    ),
    "adventure": (
        "Organize an adventure trip to London for 4 friends for 5 days. We "
        "want traditional culture plus modern experiences and outdoor "
        "activities. Budget $2500 per person."
    ),
    "cultural": (
        "Explore Paris for cultural experiences: museums, theaters, art "
        "galleries, culinary tours. 5 days for 2 people, mid-range budget "
        "around $3500 total."
    ),
}


async def main():
    """Main execution function."""
    load_dotenv()
    
    print("🌍 Enhanced Multi-Agent Travel Planning System (OpenAI Agents)")
    print("="*70)
    
    # Check configuration
    if not (os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        print(
            "❌ Please set AZURE_OPENAI_* or OPENAI_API_KEY environment "
            "variables"
        )
        return
    
    # Show sample requests
    print("\n📝 Sample requests you can try:\n")
    for trip_type, request in SAMPLE_REQUESTS.items():
        print(f"{trip_type.title()}:")
        print(f'  "{request}"\n')
    
    print("="*70)
    
    # Get user input
    user_input = input(
        "\n✈️ Describe your travel plans (or press Enter for sample): "
    ).strip()
    
    if not user_input:
        user_input = SAMPLE_REQUESTS["business"]
        print(f"\n🎯 Using sample: {user_input}")
    
    try:
        # Run the planning workflow
        final_plan = await run_travel_planning(user_input)
        
        # Display the final plan
        print("\n" + "="*70)
        print("🎉 COMPLETE TRAVEL PLAN")
        print("="*70)
        print(final_plan)
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error during planning: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Ensure telemetry is flushed
        try:
            trace.get_tracer_provider().force_flush()
        except Exception:  # noqa: BLE001
            pass
    
    print("\n🎊 Travel planning completed!")
    print(
        "Thank you for using the Enhanced Multi-Agent Travel Planning System!"
    )

if __name__ == "__main__":
    asyncio.run(main())
