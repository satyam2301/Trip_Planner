import os
from typing import Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
try:
    from backend.tools.llm_provider import get_llm
    from backend.tools.weather_tool import weather_search
except ImportError:
    from tools.llm_provider import get_llm
    from tools.weather_tool import weather_search

load_dotenv()

llm = get_llm(max_tokens=1500, temperature=0.1)

class WeatherQueryExtraction(BaseModel):
    cities: list[str] = Field(
        description="List of all cities or tourist destinations the user wants to visit. E.g., ['Goa'] for Goa; ['Kyoto'] if user requested Kyoto; ['Tokyo', 'Kyoto', 'Nagoya'] for multi-city; ['Tokyo'] if only 'Japan' was mentioned."
    )
    primary_city: str = Field(
        description="The primary arrival or gateway city/region where international flights will land (e.g. 'Goa' for Goa; 'Tokyo' for a multi-city Japan trip; 'Paris' for France)."
    )
    duration_days: int = Field(
        default=7,
        description="Number of days the user wants to travel (e.g., 3 for 3-day weekend, 5 for 5 days, 10 for 10-day trip, 14 for 2 weeks). Default to 7 if unspecified."
    )
    month: Optional[int] = Field(
        None,
        description="Month of travel as an integer from 1 to 12 if specified in query (e.g., July -> 7, December -> 12). If not specified, null."
    )
    is_upcoming: bool = Field(
        True,
        description="True if trip is upcoming soon (next 14 days) or no specific future month is specified. False if a specific future month is mentioned."
    )

class WeatherSynthesisOutput(BaseModel):
    recommended_start_date: str = Field(
        description="The exact departure date (YYYY-MM-DD) for the recommended travel window. Must be a valid date string (e.g. '2027-07-22' or '2026-10-15')."
    )
    analysis: str = Field(
        description="Concise markdown report explaining the recommended window, temperatures, and rain comparison across cities."
    )

WEATHER_EXTRACTION_PROMPT = """You are a travel destination and date specialist.
Analyze the user's travel request and extract:
1. cities: List of destination cities or popular regions the user wants to visit.
   - Rule A: If the user explicitly names one or more cities or popular regions/states (e.g., "trip to Goa", "Goa", "Bali", "Kerala", "Kyoto", "visit Tokyo and Kyoto"), extract those exact names (e.g. ["Goa"], ["Bali"], ["Kerala"]).
   - Rule B: ONLY if the user mentions a country without any specific city/region (e.g., "trip to Japan", "trip to France"), default to the primary gateway city (e.g., ["Tokyo"], ["Paris"]).
2. primary_city: The main entry city or region (e.g. "Goa", "Tokyo", "Paris", or the first destination mentioned).
3. duration_days: Number of days for the trip (e.g. '3 days' -> 3, '5 day trip' -> 5, '10 days' -> 10, '2 weeks' -> 14). If unspecified, default to 7.
4. month: Month number 1-12 if mentioned (e.g., 'in July' -> 7, 'in December' -> 12). Otherwise null.
5. is_upcoming: False if a specific future month is mentioned, True if upcoming soon or unspecified.

Return valid structured data with keys "cities", "primary_city", "duration_days", "month", and "is_upcoming".
"""


WEATHER_SYNTHESIS_TEMPLATE = """You are an expert travel climate advisor.
The traveler wants to plan a {duration_days}-day trip to {destination}.
Review the following weather/climate data across the visited destinations.

Your task:
1. Identify the optimal {duration_days}-day period/dates with the lowest rainfall and comfortable temperatures across the destination(s).
2. In 'recommended_start_date', provide the EXACT start date of this optimal window in YYYY-MM-DD format.
   - If live forecast data (next 14 days) is provided, select the best starting date from the live forecast table (e.g. within the next 2-10 days).
   - If historical climate data for a future month is provided, choose the best week's start date within that month (use year 2026 or 2027 as appropriate).
3. In 'analysis', provide a concise markdown report covering:
   - **Destination**: Explicitly confirm the intended destination (e.g., Goa, India - not foreign homonyms).
   - **Best {duration_days}-Day Window**: The recommended dates and why.
   - **Climate & Conditions**: Expected high/low temperatures, rain risk, and comfort index.

Do NOT include clothing, packing, or activity suggestions (those will be handled in the final itinerary).
Return valid structured output matching the schema.
"""

weather_extractor = llm.with_structured_output(WeatherQueryExtraction)

synthesis_extractor = llm.with_structured_output(WeatherSynthesisOutput)

def ensure_future_date(date_str: str) -> str:
    """Helper to ensure the recommended date is strictly in the future."""
    try:
        dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
        now = datetime.now()
        while dt < now:
            dt = dt.replace(year=dt.year + 1)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

def weather_agent_node(state: dict) -> dict:
    """
    LangGraph node that runs first in the travel planner.
    Analyzes destination weather/climate to determine the optimal travel window
    and outputs the exact recommended start date for the Flight Agent.
    """
    user_query = state.get("user_query", "")
    
    # Step 1: Extract destination cities, duration, and timeframe
    try:
        extraction: WeatherQueryExtraction = weather_extractor.invoke([
            SystemMessage(content=WEATHER_EXTRACTION_PROMPT),
            HumanMessage(content=user_query)
        ])
        cities = extraction.cities if extraction.cities else ["Tokyo"]
        primary_city = extraction.primary_city or cities[0]
        duration_days = extraction.duration_days or 7
        month = extraction.month
        is_upcoming = extraction.is_upcoming
    except Exception as e:
        cities = ["Tokyo"]
        primary_city = "Tokyo"
        duration_days = 7
        month = None
        is_upcoming = True

    # Step 2: Fetch weather data for each city
    weather_reports = []
    for city in cities[:3]:
        try:
            report = weather_search(city=city, month=month, is_upcoming=is_upcoming)
            weather_reports.append(report)
        except Exception as e:
            weather_reports.append(f"Unable to fetch weather data for {city}: {str(e)}")

    raw_weather_data = "\n\n---\n\n".join(weather_reports)
    destination_str = ", ".join(cities)

    # Step 3: LLM analyzes the weather and determines the exact start date
    try:
        synthesis_prompt = WEATHER_SYNTHESIS_TEMPLATE.format(
            duration_days=duration_days,
            destination=destination_str
        )
        synthesis_res: WeatherSynthesisOutput = synthesis_extractor.invoke([
            SystemMessage(content=synthesis_prompt),
            HumanMessage(content=f"User Query: {user_query}\n\nWeather Data:\n{raw_weather_data}")
        ])
        raw_start_date = synthesis_res.recommended_start_date
        travel_date = ensure_future_date(raw_start_date)
        weather_analysis = synthesis_res.analysis.strip()
    except Exception as e:
        travel_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        weather_analysis = raw_weather_data

    combined_weather_report = f"{raw_weather_data}\n\n### 🌦️ Weather & Best {duration_days}-Day Window Recommendation:\n{weather_analysis}"

    return {
        "destination": destination_str,
        "duration_days": duration_days,
        "travel_date": travel_date,
        "weather_results": combined_weather_report,
        "message": [AIMessage(content=f"Weather Analysis for {duration_days}-day trip to {destination_str} (Best departure date: {travel_date}):\n\n{weather_analysis}")],
        "llm_calls": state.get("llm_calls", 0) + 2
    }
