import os
import json
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
try:
    from backend.tools.places_tool import places_search, fetch_attraction_images
    from backend.tools.currency_tool import get_live_exchange_rate
    from backend.tools.llm_provider import get_llm
except ImportError:
    from tools.places_tool import places_search, fetch_attraction_images
    from tools.currency_tool import get_live_exchange_rate
    from tools.llm_provider import get_llm

load_dotenv()

llm = get_llm(max_tokens=3000, temperature=0.2)

# --- Pydantic Models for Day Allocation & Preferences ---

class CityPlanPreference(BaseModel):
    cities: list[str] = Field(
        description="List of destination cities (e.g. ['Tokyo', 'Kyoto'] or ['Goa'])."
    )
    days_per_city: dict[str, int] = Field(
        description="Allocation of total trip days per city summing to duration_days (e.g. {'Tokyo': 4, 'Kyoto': 3})."
    )
    top_landmarks: list[str] = Field(
        default_factory=list,
        description="Top 3 to 6 iconic landmarks, beaches, or historic sights to visit (e.g. ['Fort Aguada', 'Basilica of Bom Jesus', 'Palolem Beach', 'Dudhsagar Falls'] for Goa; ['Senso-ji Temple', 'Shibuya Crossing', 'Fushimi Inari Shrine'] for Japan)."
    )
    dietary_preference: Optional[str] = Field(
        None,
        description="Dietary preference if mentioned (e.g. 'vegetarian', 'jain', 'vegan', 'halal')."
    )
    interests: Optional[str] = Field(
        None,
        description="Travel interests if mentioned (e.g. 'temples', 'culture', 'shopping', 'beaches', 'nature', 'nightlife')."
    )

ALLOCATION_PROMPT = """You are a travel itinerary planner.
Analyze the user request, destination cities, and total trip duration to allocate days across cities, identify the top iconic landmarks/sights, and extract travel interests/dietary preferences.

Rules:
1. cities: List all visited destination cities. If only country is provided (e.g. 'Japan'), use primary entry city (['Tokyo']).
2. days_per_city: Allocate total trip days logically across cities. The sum must equal duration_days.
   - Example 7 days Tokyo + Kyoto: {"Tokyo": 4, "Kyoto": 3}
   - Example 3 days Goa: {"Goa": 3}
3. top_landmarks: Extract 3 to 6 famous, iconic landmarks, temples, forts, beaches, or monuments that the user must visit.
   - Example Goa: ["Fort Aguada", "Basilica of Bom Jesus", "Palolem Beach", "Dudhsagar Falls", "Calangute Beach"]
   - Example Paris: ["Eiffel Tower", "Louvre Museum", "Notre-Dame Cathedral", "Arc de Triomphe"]
4. dietary_preference: 'vegetarian', 'jain', 'vegan', 'halal', or null if unspecified.
5. interests: Specific interests mentioned by user (e.g. 'beaches', 'temples', 'shopping', 'theme parks'), or null.

Return valid structured data with keys "cities", "days_per_city", "top_landmarks", "dietary_preference", and "interests".
"""

SYNTHESIS_PROMPT = """You are an expert local guide and culinary specialist catering to travelers.
Synthesize the live attractions, sightseeing, and dining research below into a rich, structured guide organized by city and tailored to the number of days spent in each city.

Trip Details:
- Destinations & Days: {destinations_and_days}
- Total Trip Duration: {duration_days} days
- Dietary Preference: {dietary_preference}
- Interests: {interests}
- Live Currency Rate: 1 USD = ₹{live_rate:.2f} INR

Available Visual Photos of Attractions:
{visual_photos_text}

Research Data across Cities:
{research_data_text}

Instructions:
For EACH destination city (e.g., Tokyo — 4 Days, Kyoto — 3 Days; or Goa — 3 Days):
1. 🏛️ **Top Sights & Experiences** (Scale appropriately: ~4-6 sights):
   - Group logically by area/neighborhood to minimize travel time.
   - For each sight: Name, Neighborhood, What makes it special, Typical Duration (e.g. 1.5-2 hrs), and Approximate Entry Ticket (in both USD and INR, or Free if applicable).
   - If an authentic photo is available for a sight in the Visual Photos list above, embed it right below the sight header as `![Sight Name](image_url)` followed by an italicized caption `*Caption*`.
2. 🍜 **Iconic Local Foods to Try**:
   - 3-4 authentic regional specialties (e.g., Goan Fish Curry, Bebinca, Poi bread; or Ramen, Matcha sweets).
3. 🥗 **Dining & Indian/Vegetarian Recommendations**:
   - Provide recommended restaurants including vegetarian-friendly and Indian dining options with approximate meal budget per person.
4. 🚇 **Local Transit & Smart Travel Tips**:
   - Best transit option or rental recommendation (e.g., scooter/car rental in Goa, or Subway 72hr Ticket in Tokyo).
   - Navigation links: Include the Google Maps links provided.

End with a brief **Estimated Daily Sightseeing & Food Budget per person** for the trip.
Format with clean, professional markdown headers and bullet points.
"""

allocation_extractor = llm.with_structured_output(CityPlanPreference)


def places_agent_node(state: dict) -> dict:
    """
    LangGraph node for discovering sights, attractions, and dining experiences.
    Multi-city aware: allocates trip days across each destination city and gathers
    tailored sightseeing, authentic web photos, and culinary recommendations.
    """
    user_query = state.get("user_query", "")
    existing_dest = state.get("destination", "")
    duration_days = state.get("duration_days", 7)

    # Fetch live currency rate for accurate ticket and meal conversion
    live_rate = get_live_exchange_rate("USD", "INR")

    # Step 1: Extract cities, day allocation, and interests
    try:
        pref: CityPlanPreference = allocation_extractor.invoke([
            SystemMessage(content=ALLOCATION_PROMPT),
            HumanMessage(content=f"User Query: {user_query}\nDestination: {existing_dest}\nDuration Days: {duration_days}")
        ])
        cities = pref.cities if pref.cities else [existing_dest or "Tokyo"]
        days_per_city = pref.days_per_city or {}
        top_landmarks = pref.top_landmarks or []
        dietary_pref = pref.dietary_preference or "Indian & Vegetarian friendly options"
        interests = pref.interests
    except Exception:
        cities = [c.strip() for c in existing_dest.split(",") if c.strip()] if existing_dest else ["Tokyo"]
        days_per_city = {cities[0]: duration_days}
        top_landmarks = []
        dietary_pref = "Indian & Vegetarian friendly options"
        interests = None

    # Ensure allocated days equal total duration_days
    allocated_sum = sum(days_per_city.get(c, 0) for c in cities)
    if allocated_sum != duration_days:
        base = max(1, duration_days // len(cities))
        rem = duration_days % len(cities)
        days_per_city = {c: base + (1 if i < rem else 0) for i, c in enumerate(cities)}

    dest_summary = ", ".join([f"{c} ({days_per_city.get(c, 1)} days)" for c in cities])

    # Step 2: Fetch real web photos for the identified landmarks
    primary_city = cities[0]
    gathered_images = []
    if top_landmarks:
        gathered_images = fetch_attraction_images(top_landmarks, primary_city)
    
    # If no landmarks were in extraction, fallback to searching for iconic city sights
    if not gathered_images:
        fallback_landmarks = [f"{primary_city} landmark", f"{primary_city} beach or temple", f"{primary_city} scenic view"]
        gathered_images = fetch_attraction_images(fallback_landmarks, primary_city)

    # Format visual photos markdown text for the LLM
    visual_photos_lines = []
    for img in gathered_images:
        visual_photos_lines.append(f"- Sight: {img['name']} | URL: {img['url']}")
    visual_photos_text = "\n".join(visual_photos_lines) if visual_photos_lines else "No specific photo URLs available."

    # Step 3: Search live attractions and dining for each city
    research_blocks = []
    for city in cities[:3]:
        city_days = days_per_city.get(city, 1)
        data = places_search(
            city=city,
            days=city_days,
            interests=interests,
            dietary_preference=dietary_pref
        )

        # Merge any additional images returned by Tavily
        for web_img in data.get("images", [])[:2]:
            if not any(g["url"] == web_img for g in gathered_images):
                gathered_images.append({
                    "name": f"{city} Highlight",
                    "city": city,
                    "url": web_img
                })

        city_text = f"### Research for {city} ({city_days} Days):\n"
        city_text += f"Attractions Summary: {data.get('attractions_summary', '')}\n"
        for r in data.get("attractions_raw", [])[:3]:
            city_text += f"- Sight: {r.get('title', '')} | {r.get('content', '')[:250]}\n"
        
        city_text += f"\nDining Summary: {data.get('dining_summary', '')}\n"
        for r in data.get("dining_raw", [])[:3]:
            city_text += f"- Restaurant/Food: {r.get('title', '')} | {r.get('content', '')[:250]}\n"

        maps_links = data.get("maps_links", {})
        if maps_links:
            city_text += f"\nDiscovery Maps: [Explore {city} Attractions on Google Maps]({maps_links.get('attractions_map', '#')}) | [Explore {city} Dining]({maps_links.get('restaurants_map', '#')})\n"

        research_blocks.append(city_text)

    combined_research = "\n\n".join(research_blocks)

    # Step 4: Synthesize comprehensive guide with LLM with photos embedded
    try:
        synthesis_prompt = SYNTHESIS_PROMPT.format(
            destinations_and_days=dest_summary,
            duration_days=duration_days,
            dietary_preference=dietary_pref,
            interests=interests or "Iconic sights, culture, food, and local experiences",
            live_rate=live_rate,
            visual_photos_text=visual_photos_text,
            research_data_text=combined_research
        )

        response = llm.invoke([
            SystemMessage(content="You are an expert travel guide. Format in structured, engaging markdown with embedded photos."),
            HumanMessage(content=synthesis_prompt)
        ])
        places_report = response.content.strip()
    except Exception as e:
        places_report = f"# 🏛️ Attractions & Dining Guide ({duration_days} Days)\n\n{combined_research}"

    return {
        "places_results": places_report,
        "place_images": gathered_images,
        "message": [AIMessage(content=places_report)],
        "llm_calls": state.get("llm_calls", 0) + 2
    }
