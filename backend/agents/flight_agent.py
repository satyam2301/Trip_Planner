import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
try:
    from backend.tools.llm_provider import get_llm
    from backend.tools.flight_tool import flight_search
except ImportError:
    from tools.llm_provider import get_llm
    from tools.flight_tool import flight_search

load_dotenv()

llm = get_llm(max_tokens=1000, temperature=0.1)

class RouteExtraction(BaseModel):
    departure_iata: str = Field(
        description="3-letter IATA code of departure airport (e.g., 'DEL' for Delhi, 'BOM' for Mumbai, 'JFK' for New York). If departure is omitted by the user, default to 'DEL'."
    )
    arrival_iata: str = Field(
        description="3-letter IATA code of primary arrival airport or metropolitan city area (e.g., 'TYO' for Tokyo, 'LON' for London, 'NYC' for New York, 'PAR' for Paris)."
    )
    date: Optional[str] = Field(
        None,
        description="Travel departure date in YYYY-MM-DD format if specified in the user request. Otherwise null."
    )

ROUTE_EXTRACTION_PROMPT = """You are an international aviation route specialist.
Analyze the user's travel request and extract the departure and destination airport IATA codes (3-letter uppercase codes).

Rules:
1. Metropolitan Area Codes (Crucial for Multi-Airport Cities):
   Always prefer the metropolitan city-wide IATA code when a city has multiple international airports, so flight search discovers all carriers (including flag carriers like Air India, ANA, JAL and regional airlines):
   - Tokyo / Japan -> TYO (searches both Haneda HND and Narita NRT)
   - London / UK -> LON (searches Heathrow LHR, Gatwick LGW, Stansted STN)
   - New York -> NYC (searches JFK, EWR, LGA)
   - Paris / France -> PAR (searches CDG, ORY)
   - Rome / Italy -> ROM (searches FCO, CIA)
   - Milan / Italy -> MIL (searches MXP, LIN, BGY)
   - Seoul / South Korea -> SEL (searches ICN, GMP)
   - Bangkok / Thailand -> BKK
   - Singapore -> SIN
   - Dubai / UAE -> DXB
   - Sydney / Australia -> SYD
   - Bali / Indonesia -> DPS
2. For Indian origin/destinations:
   - Delhi -> DEL
   - Mumbai -> BOM
   - Bangalore / Bengaluru -> BLR
   - Goa -> GOI
3. If the user does NOT mention a departure place (e.g., "Plan a 7-day trip to Japan"), default departure_iata to "DEL".
4. If an exact date is mentioned in the query (e.g. 2026-10-15), format as YYYY-MM-DD; otherwise null.
5. Return only the valid JSON matching keys "departure_iata", "arrival_iata", and "date".
"""

route_extractor = llm.with_structured_output(RouteExtraction)

def flight_agent_node(state: dict) -> dict:
    """
    LangGraph node for searching flights based on user query and weather recommendations.
    Uses the exact travel_date established by the Weather Agent (or extracted from query)
    to fetch real-time Google Flight options and exact live pricing for that date.
    """
    user_query = state.get("user_query", "")
    weather_results = state.get("weather_results", "")
    
    # Priority 1: Use the exact optimal travel date determined by the Weather Agent!
    state_travel_date = state.get("travel_date")
    
    # Step 1: Extract departure and arrival IATA codes using LLM
    try:
        extraction_res: RouteExtraction = route_extractor.invoke([
            SystemMessage(content=ROUTE_EXTRACTION_PROMPT),
            HumanMessage(content=f"User Query: {user_query}\nWeather Context: {weather_results[:300]}")
        ])
        dep_iata = extraction_res.departure_iata.strip().upper()
        arr_iata = extraction_res.arrival_iata.strip().upper()
        travel_date = state_travel_date or extraction_res.date
    except Exception as e:
        err_msg = f"Unable to identify flight route from query: {str(e)}"
        return {
            "flight_results": err_msg,
            "message": [AIMessage(content=err_msg)],
            "llm_calls": state.get("llm_calls", 0) + 1
        }

    # Step 2: Fetch 5 live Google Flights with exact pricing for the chosen date
    try:
        flights_data = flight_search(departure_iata=dep_iata, arrival_iata=arr_iata, date=travel_date)
        flight_results = f"Route: {dep_iata} -> {arr_iata} (Departure Date: {travel_date})\n\n{flights_data}"
    except Exception as e:
        flight_results = f"Error fetching flights between {dep_iata} and {arr_iata}: {str(e)}"

    return {
        "travel_date": travel_date,
        "flight_results": flight_results,
        "message": [AIMessage(content=f"Found Google Flight options for route {dep_iata} -> {arr_iata} on {travel_date}:\n\n{flight_results}")],
        "llm_calls": state.get("llm_calls", 0) + 1
    }
