import os
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
try:
    from backend.tools.currency_tool import get_live_exchange_rate
    from backend.tools.llm_provider import get_llm
except ImportError:
    from tools.currency_tool import get_live_exchange_rate
    from tools.llm_provider import get_llm

load_dotenv()

llm = get_llm(max_tokens=4000, temperature=0.3)

ITINERARY_MASTER_PROMPT = """You are a master travel architect and luxury concierge.
Synthesize the complete travel intelligence gathered by specialized research agents into an authoritative, day-by-day Master Travel Plan & Financial Ledger.

Trip Parameters:
- User Request: {user_query}
- Primary Destination: {destination}
- Duration: {duration_days} Days / {duration_nights} Nights
- Recommended Travel Window: {travel_dates}
- Live Exchange Rate: 1 USD = ₹{live_rate:.2f} INR (official live rate)

=== INPUT INTELLIGENCE FROM SPECIALIZED AGENTS ===

1. 🌤️ CLIMATE & TIMING INTELLIGENCE:
{weather_data}

2. ✈️ FLIGHT INTELLIGENCE & FARE BENCHMARKS:
{flight_data}

3. 🏨 ACCOMMODATIONS & VERIFIED BOOKING LINKS:
{hotel_data}

4. 🏛️ ATTRACTIONS, SIGHTSEEING & DINING GUIDE:
{places_data}

5. 📸 REAL VISUAL DESTINATION & ATTRACTION PHOTOS:
{photos_data}

=== YOUR TASK & REPORT STRUCTURE ===

Generate a beautifully formatted, exhaustive markdown travel document with the following 4 sections:

# 🗺️ Master Travel Itinerary: {destination} ({duration_days} Days)

### 📌 Trip Snapshot
- **Dates**: {travel_dates} (Optimized for favorable climate and flight deals)
- **Destinations Covered**: Cities with night allocation
- **Pacing & Style**: e.g., Cultural immersion, balanced sightseeing, foodie-friendly
- **Key Accommodations**: Summarize the top recommended hotel per city with its direct booking link

---

### 📅 Day-by-Day Master Itinerary (Day 1 to Day {duration_days})
For every single day (Day 1 through Day {duration_days}), provide:
- **Header**: `#### Day X: [Catchy Title] — [City / Region]`
- **Visual Highlight**: If an authentic photo from the Visual Photos list matches this day's highlight landmark, embed it right below the header as `![Landmark Name](image_url)` followed by `*Short description/caption*`.
- **Morning**: Specific sights/attractions, opening timing, neighborhood, and transit tip.
- **Afternoon**: Activities, scenic spots, or cultural visits.
- **Lunch & Dinner Recommendations**: Specific dishes to try and recommended restaurants (including vegetarian/Indian friendly options from research).
- **Evening**: Night view, neighborhood stroll, market walk, or relaxation.
- **Inter-city Transit** (if transferring between cities, e.g. bullet train from Tokyo to Kyoto): Clearly explain travel time, train line, and luggage handling.

---

### 💰 Comprehensive Financial Ledger & Grand Total Trip Budget
Provide a clean Markdown summary table with realistic calculations in both INR and USD:
| Expense Category | Details / Basis | Estimated Cost (INR) | Estimated Cost (USD) |
| :--- | :--- | :--- | :--- |
| **Flights (Round-Trip)** | From flight agent research | ₹... | $... |
| **Hotels & Lodging** | From hotel agent research ({duration_nights} nights) | ₹... | $... |
| **Local Transportation** | Metro passes, IC cards, bullet train/taxis | ₹... | $... |
| **Sightseeing & Entry Fees** | Top monuments, museum tickets, attractions | ₹... | $... |
| **Food & Dining** | ~3 meals/day + snacks/cafes per person | ₹... | $... |
| **Contingency & Buffer (10%)** | Emergency, shopping, unforeseen fees | ₹... | $... |
| **GRAND TOTAL ESTIMATED BUDGET** | **All-Inclusive Estimate per Person** | **₹...** | **$...** |

---

### 🎒 Pre-Trip Checklist & Practical Traveler Advice
Provide essential, actionable guidance:
1. **Visa Requirements**: Visa / eVisa requirements, essential documents (hotel vouchers, return flight).
2. **Connectivity & Navigation**: Best eSIM / Pocket WiFi recommendation and navigation apps.
3. **Money & Payments**: Cash vs card advice, Forex cards, 7-Eleven ATM withdrawals.
4. **Packing Essentials**: Weather-tailored packing advice based on the climate analysis.
"""

def itinerary_agent_node(state: dict) -> dict:
    """
    LangGraph node for synthesizing the final Master Travel Itinerary & Budget Ledger.
    Takes inputs from weather, flight, hotel, and places agents to produce an all-in-one
    day-by-day travel plan with real photos and financial breakdown.
    """
    user_query = state.get("user_query", "")
    destination = state.get("destination", "Destination")
    duration_days = state.get("duration_days", 7)
    duration_nights = max(1, duration_days - 1)
    travel_date = state.get("travel_date", "Flexible")

    weather_data = state.get("weather_results", "Weather data not available.")
    flight_data = state.get("flight_results", "Flight data not available.")
    hotel_data = state.get("hotel_results", "Hotel data not available.")
    places_data = state.get("places_results", "Attractions and dining data not available.")
    place_images = state.get("place_images", [])

    photos_lines = []
    for img in place_images[:8]:
        photos_lines.append(f"- {img.get('name')} ({img.get('city', '')}): {img.get('url')}")
    photos_data = "\n".join(photos_lines) if photos_lines else "No specific photos provided."

    live_rate = get_live_exchange_rate("USD", "INR")

    prompt = ITINERARY_MASTER_PROMPT.format(
        user_query=user_query,
        destination=destination,
        duration_days=duration_days,
        duration_nights=duration_nights,
        travel_dates=travel_date,
        live_rate=live_rate,
        weather_data=weather_data[:3000],
        flight_data=flight_data[:2500],
        hotel_data=hotel_data[:3000],
        places_data=places_data[:3500],
        photos_data=photos_data
    )

    try:
        response = llm.invoke([
            SystemMessage(content="You are the lead travel architect. Produce an exhaustive, inspiring, and meticulously organized master travel itinerary."),
            HumanMessage(content=prompt)
        ])
        master_itinerary = response.content.strip()
    except Exception as e:
        master_itinerary = f"# 🗺️ Master Travel Itinerary for {destination}\n\nUnable to synthesize itinerary: {str(e)}"

    return {
        "itinerary": master_itinerary,
        "message": [AIMessage(content=master_itinerary)],
        "llm_calls": state.get("llm_calls", 0) + 1
    }
