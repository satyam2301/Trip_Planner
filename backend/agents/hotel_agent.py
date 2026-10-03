import os
import json
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from backend.tools.hotel_tool import hotel_search, generate_hotel_booking_links  
from backend.tools.currency_tool import get_live_exchange_rate, convert_currency
from backend.tools.llm_provider import get_llm

load_dotenv()

llm = get_llm(max_tokens=3000, temperature=0.2)

# --- Pydantic Models ---

class HotelPreferences(BaseModel):
    """Extracted from user query: which cities, how many nights, budget level."""
    cities: list[str] = Field(
        description="List of destination cities to stay in (e.g. ['Tokyo', 'Kyoto'])."
    )
    nights_per_city: dict[str, int] = Field(
        description="Dict mapping each city to nights (e.g. {'Tokyo': 4, 'Kyoto': 3})."
    )
    budget_tier: str = Field(
        default="mid-range",
        description="Budget tier: 'cheap', 'low budget', 'budget', 'mid budget', 'mid range', 'balanced', 'high', or 'luxury'."
    )
    neighborhood_preference: Optional[str] = Field(
        None,
        description="Preferred neighborhood or area if specified."
    )

class HotelItem(BaseModel):
    name: str = Field(description="Exact real hotel property name mentioned in the search data")
    city: str = Field(description="City where the hotel is located")
    estimated_nightly_usd: int = Field(description="Realistic estimated nightly rate in USD explicitly found in search data or market rate (convert from local currency if mentioned)")
    neighborhood: str = Field(description="Specific neighborhood or district in the city")
    vibe: str = Field(description="Traveler vibe, atmosphere, or style")
    amenities: str = Field(description="Top key amenities (e.g. WiFi, Onsen, Breakfast, Metro access)")

class CityHotelsExtraction(BaseModel):
    hotels: list[HotelItem] = Field(description="List of 2-3 real hotels found in the search data for this city")

# --- Prompts ---

PREFERENCE_EXTRACTION_PROMPT = """You are an accommodation specialist.
Extract hotel preferences from the travel request.

Rules:
1. cities: List all destination cities needing lodging.
   - Multi-city (e.g. "Tokyo and Kyoto") -> include all cities.
   - Country-only (e.g. "Japan") -> use primary entry city (e.g. ["Tokyo"]).
2. nights_per_city: Allocate total nights logically. Sum must equal duration_days.
   Example: 7 days Tokyo+Kyoto -> {"Tokyo": 4, "Kyoto": 3}
3. budget_tier: Infer tier from user keywords:
   - 'cheap', 'hostel', 'zostel', 'backpacker', 'dorm', 'low budget', 'economy', 'budget', 'under 1000', 'under 800', 'student', 'affordable' -> 'budget / hostel'
   - 'mid budget', 'mid-range', 'mid range', 'moderate', 'value', '3-star' -> 'mid-range'
   - 'high', 'luxury', '5-star', 'resort', 'premium' -> 'luxury'
   - If unspecified or balanced -> 'balanced' (or 'mid-range').
4. neighborhood_preference: Specific area if mentioned, else null.

Return valid JSON with keys "cities", "nights_per_city", "budget_tier", "neighborhood_preference".
"""

HOTEL_EXTRACTION_PROMPT = """You are an accommodation data extractor.
Analyze the live search results for {city} (requested tier: {budget_tier}) and extract 2 to 3 real, specific properties mentioned in the text.

Search Data:
{search_data}

Rules:
1. Extract ONLY real accommodation/property names explicitly found in the search data (e.g. "The Hosteller Goa, Anjuna", "Zostel Goa", "goSTOPS Vagator", "Park Hotel Tokyo"). Do NOT invent properties.
2. Extract the realistic nightly room or dorm bed rate in USD as explicitly found in the search text (convert to USD if quoted in local currency like INR, JPY, EUR).
   CRITICAL BUDGET ALIGNMENT:
   - If requested tier is 'budget / hostel' or 'budget' or 'low budget':
     * The traveler specifically wants low-budget backpacker accommodations like hostels, dorm beds, capsule hotels, or budget guesthouses (e.g. Zostel, The Hosteller, goSTOPS, etc. in India which cost ₹300 - ₹900 INR per night, approximately $4 - $10 USD).
     * Prioritize extracting dorm bed / budget room rates (~$4 to $10 USD / ₹350 to ₹900 INR for India/Southeast Asia, or $20 - $35 USD for Europe/Japan).
     * Do NOT extract 4-star/5-star luxury hotels (like ibis, Marriott, Taj, etc.) costing ₹5,000 - ₹15,000+ when the user asked for low budget / hostels!
   - If requested tier is 'mid budget' / 'mid-range' / 'balanced':
     * Comfortable 3-star/4-star private hotel rooms ($40 - $100 USD / ₹3,500 - ₹9,500 INR).
   - If requested tier is 'luxury' / 'high':
     * 4-star/5-star luxury resorts, heritage villas, premium boutique hotels ($150 - $400+ USD).
3. Identify neighborhood/district, ambiance/vibe, and key amenities (Wi-Fi, lockers, café, pool, social activities).

Return valid JSON with key "hotels".
"""

HOTEL_SYNTHESIS_PROMPT = """You are an accommodation specialist and travel advisor.
Synthesize the curated hotel research into a beautifully structured, comprehensive accommodation guide.

Trip Overview:
- Destinations & Nights Allocation: {destinations_and_nights}
- Total Duration: {duration_days} nights
- Dates / Window: {travel_dates}
- Budget Tier: {budget_tier}
- Live Currency Conversion Rate: 1 USD = ₹{live_rate:.2f} INR (fetched live from European Central Bank)

Curated Lodging Data with Verified Booking Links:
{hotel_data_text}

Instructions:
1. Present each destination city with its allocated nights.
2. For each accommodation property:
   - Name & Neighborhood (highlight convenient beach / metro / transit access and social vibe)
   - Property Type: Explicitly identify if it is a Social Backpacker Hostel (Dorm Bed / Private Room), Guesthouse, Boutique Hotel, or Resort.
   - Estimated Nightly Rate (in both INR and USD as provided in the data). For low-budget/hostels, highlight the per-bed dorm price (e.g. ~₹500 - ₹800/night).
   - Estimated Stay Cost for that city's allocated nights (Nightly rate × nights)
   - Vibe & Key Amenities (AC, Wi-Fi, lockers, café, swimming pool, community events)
   - Direct Booking Links: Use the EXACT markdown links provided in the data (Google Hotels and Booking.com). Do NOT create or alter URLs.
3. City Exploration: Include the city-wide search links provided.
4. Accommodation Budget & Total Cost Summary:
   - Provide a clear cost breakdown using the verified live rates provided.
   - Show the estimated cost per city for the allocated nights.
   - Show the Grand Total lodging cost for the entire trip (both in USD and INR).
   - For low budget / hostels, highlight how choosing community hostels (Zostel, The Hosteller, goSTOPS) keeps the entire accommodation budget remarkably affordable (e.g. under ₹2,000 - ₹2,500 total).
   - Add a brief practical booking tip for travelers (e.g., booking dorms in advance for weekend peak season).
"""

preference_extractor = llm.with_structured_output(HotelPreferences)
hotel_data_extractor = llm.with_structured_output(CityHotelsExtraction)


def _extract_city_hotels(city: str, search_data: str, budget_tier: str) -> list[HotelItem]:
    """
    Extracts 2-3 real hotels from Tavily search data using structured LLM output,
    with JSON fallback if needed.
    """
    try:
        result: CityHotelsExtraction = hotel_data_extractor.invoke([
            SystemMessage(content=HOTEL_EXTRACTION_PROMPT.format(city=city, budget_tier=budget_tier, search_data=search_data)),
            HumanMessage(content=f"Extract 2-3 real hotel properties found in the search data for {city}.")
        ])
        if result and result.hotels:
            return result.hotels
    except Exception:
        # Fallback to direct JSON parsing if structured output fails
        try:
            resp = llm.invoke([
                SystemMessage(content=HOTEL_EXTRACTION_PROMPT.format(city=city, budget_tier=budget_tier, search_data=search_data)),
                HumanMessage(content="Return JSON with key 'hotels'.")
            ])
            text = resp.content.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                hotels_list = []
                for h in data.get("hotels", []):
                    raw_usd = h.get("estimated_nightly_usd", 0)
                    try:
                        usd_val = int(raw_usd) if raw_usd and int(raw_usd) > 0 else 0
                    except Exception:
                        usd_val = 0

                    hotels_list.append(HotelItem(
                        name=h.get("name", "Recommended Hotel"),
                        city=city,
                        estimated_nightly_usd=usd_val,
                        neighborhood=h.get("neighborhood", "Central Area"),
                        vibe=h.get("vibe", "Comfortable, well-reviewed"),
                        amenities=h.get("amenities", "Free Wi-Fi, modern rooms")
                    ))
                return hotels_list
        except Exception:
            pass
    return []



def detect_budget_tier(query: str, default: str = "mid-range") -> str:
    """
    Deterministically detects budget tier from user query keywords to prevent
    LLM extraction hallucinations or default fallback issues.
    """
    q = query.lower()
    if any(k in q for k in ["low budget", "cheap", "hostel", "zostel", "backpacker", "dorm", "under 1000", "under 800", "under 600", "budget", "economy", "student", "shoestring"]):
        return "budget / hostel"
    if any(k in q for k in ["luxury", "5-star", "5 star", "resort", "premium", "high-end", "high end", "expensive", "villa"]):
        return "luxury"
    if any(k in q for k in ["mid budget", "mid-range", "mid range", "moderate", "3-star", "4-star", "balanced"]):
        return "mid-range"
    return default


def hotel_agent_node(state: dict) -> dict:
    """
    LangGraph node for hotel discovery.
    
    Architecture:
    1. LLM extracts destination cities and allocates nights across the trip.
    2. hotel_search() queries live Tavily search data for each city.
    3. LLM extracts real hotels actually found in the search results with live pricing.
    4. tools.currency_tool fetches the live internet exchange rate to accurately convert USD to INR.
    5. generate_hotel_booking_links() generates verified Google Hotels & Booking.com
       links specifically and exclusively for those discovered hotels.
    6. LLM synthesizes a complete lodging guide and calculates real-time total costs
       dynamically based on the actual recommended hotel rates.
    """
    user_query = state.get("user_query", "")
    existing_dest = state.get("destination", "")
    duration_days = state.get("duration_days", 7)
    travel_date = state.get("travel_date", "")

    # Fetch live internet foreign exchange rate (USD -> INR)
    live_rate = get_live_exchange_rate("USD", "INR")

    # Step 1: Extract cities, night allocation, and budget preferences
    detected_tier = detect_budget_tier(user_query)
    try:
        prefs: HotelPreferences = preference_extractor.invoke([
            SystemMessage(content=PREFERENCE_EXTRACTION_PROMPT),
            HumanMessage(content=f"User Query: {user_query}\nKnown Destination: {existing_dest}\nTotal Duration Days: {duration_days}")
        ])
        cities = prefs.cities if prefs.cities else [existing_dest or "Tokyo"]
        nights_per_city = prefs.nights_per_city or {}
        # Prioritize explicit user budget intent detected from query
        if detected_tier != "mid-range":
            budget_tier = detected_tier
        else:
            extracted_tier = (prefs.budget_tier or "").strip()
            budget_tier = detect_budget_tier(extracted_tier, default="mid-range")
        neighborhood = prefs.neighborhood_preference
    except Exception:
        cities = [c.strip() for c in existing_dest.split(",") if c.strip()] if existing_dest else ["Tokyo"]
        nights_per_city = {cities[0]: duration_days}
        budget_tier = detected_tier
        neighborhood = None

    # Ensure total allocated nights equals duration_days
    allocated_sum = sum(nights_per_city.get(c, 0) for c in cities)
    if allocated_sum != duration_days:
        base = max(1, duration_days // len(cities))
        remainder = duration_days % len(cities)
        nights_per_city = {c: base + (1 if i < remainder else 0) for i, c in enumerate(cities)}

    dest_summary = ", ".join([f"{c} ({nights_per_city.get(c, 1)} nights)" for c in cities])

    # Step 2 & 3: For each destination, perform Tavily search and extract real hotels
    structured_lodging_blocks = []
    llm_calls_count = 1

    for city in cities[:3]:
        city_nights = nights_per_city.get(city, 1)
        search_res = hotel_search(city=city, budget_tier=budget_tier, neighborhood=neighborhood)

        # Build search text from Tavily answer and snippets
        search_text = f"City: {city} ({city_nights} nights)\n"
        search_text += f"AI Summary: {search_res.get('answer', '')}\n"
        for r in search_res.get("raw_results", [])[:6]:
            content = r.get("content", "")[:600]
            search_text += f"- {r.get('title', '')}: {content}\n"

        # Extract specific hotels found in this search
        extracted_hotels = _extract_city_hotels(city=city, search_data=search_text, budget_tier=budget_tier)
        llm_calls_count += 1

        city_block = f"### {city} ({city_nights} Nights)\n"
        if extracted_hotels:
            for idx, h in enumerate(extracted_hotels, 1):
                # Step 4: Generate verified booking links ONLY for hotels found in search
                links = generate_hotel_booking_links(hotel_name=h.name, city=city)
                
                # Convert currency using live internet exchange rate
                nightly_usd = h.estimated_nightly_usd
                nightly_inr = convert_currency(nightly_usd, "USD", "INR")
                stay_usd = nightly_usd * city_nights
                stay_inr = convert_currency(stay_usd, "USD", "INR")

                city_block += f"{idx}. **{h.name}**\n"
                city_block += f"   - 📍 Neighborhood: {h.neighborhood}\n"
                city_block += f"   - 💰 Estimated Rate: ~${nightly_usd}/night (₹{nightly_inr:,})\n"
                city_block += f"   - 💵 Stay Total ({city_nights} nights): ~${stay_usd:,} (₹{stay_inr:,})\n"
                city_block += f"   - ⭐ Vibe & Highlights: {h.vibe}\n"
                city_block += f"   - 🛎️ Key Amenities: {h.amenities}\n"
                city_block += f"   - 🔗 Booking Links: [Google Hotels Profile]({links['google_hotels']}) | [Booking.com Listing]({links['booking_com']})\n\n"
        else:
            city_block += "No specific hotels found in search. Browse city-wide listings below.\n\n"

        city_links = search_res.get("city_links", {})
        if city_links:
            city_block += f"🔍 **Explore all {city} hotels:** [Google Hotels]({city_links.get('google_hotels', '#')}) | [Booking.com]({city_links.get('booking_com', '#')})\n"

        structured_lodging_blocks.append(city_block)

    hotel_data_text = "\n\n".join(structured_lodging_blocks)

    # Step 5: Synthesize final lodging report with dynamic cost calculation
    try:
        synthesis_prompt = HOTEL_SYNTHESIS_PROMPT.format(
            destinations_and_nights=dest_summary,
            duration_days=duration_days,
            travel_dates=travel_date or "Flexible",
            budget_tier=budget_tier,
            live_rate=live_rate,
            hotel_data_text=hotel_data_text
        )

        response = llm.invoke([
            SystemMessage(content="You are an expert travel accommodation advisor. Output complete, polished markdown."),
            HumanMessage(content=synthesis_prompt)
        ])
        hotel_report = response.content.strip()
        llm_calls_count += 1
    except Exception as e:
        # Fallback to structured text if synthesis fails
        hotel_report = f"# 🏨 Hotel Recommendations ({duration_days} Nights)\n\n{hotel_data_text}"

    return {
        "hotel_results": hotel_report,
        "message": [AIMessage(content=hotel_report)],
        "llm_calls": state.get("llm_calls", 0) + llm_calls_count
    }
