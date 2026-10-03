import os
import urllib.parse
from typing import Optional
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


def generate_hotel_booking_links(hotel_name: str, city: str) -> dict:
    """
    Generates direct deep search links for a specific hotel property
    on Google Hotels and Booking.com. Uses search query URLs which always
    resolve to the correct property without risk of broken links.
    """
    query_str = urllib.parse.quote_plus(f"{hotel_name} {city}")
    return {
        "google_hotels": f"https://www.google.com/travel/hotels?q={query_str}",
        "booking_com": f"https://www.booking.com/searchresults.html?ss={query_str}"
    }


def hotel_search(city: str, budget_tier: str = "mid-range", neighborhood: Optional[str] = None) -> dict:
    """
    Searches live hotel recommendations using Tavily and returns
    the AI answer + raw search results for the agent to process.
    
    Args:
        city: Destination city name (e.g., 'Tokyo', 'London', 'Goa').
        budget_tier: Budget tier ('budget', 'mid-range', 'luxury', or 'balanced').
        neighborhood: Specific neighborhood or preference if any.
        
    Returns:
        dict with 'answer', 'raw_results', and 'city_links'.
    """
    if not TAVILY_API_KEY:
        return {
            "answer": "Tavily API key not found. Unable to perform live hotel search.",
            "raw_results": [],
            "city_links": {}
        }

    client = TavilyClient(api_key=TAVILY_API_KEY)
    
    tier_lower = budget_tier.lower().strip()
    is_budget_or_hostel = any(k in tier_lower for k in ["budget", "cheap", "low", "hostel", "zostel", "backpacker", "dorm", "economy"])
    is_luxury = any(k in tier_lower for k in ["luxury", "5-star", "5 star", "premium", "resort", "high"])

    if is_budget_or_hostel:
        query = f"top backpacker hostels, dorm beds, Zostel, The Hosteller, goSTOPS and cheap budget stays in {city} nightly price per bed per night 2026 booking.com zostel hostelworld"
        if neighborhood:
            query = f"top backpacker hostels, Zostel, dorms and budget stays in {city} near {neighborhood} nightly price per bed 2026"
    elif is_luxury:
        query = f"top luxury 5-star hotels and luxury beach resorts in {city} room rates nightly price 2026 booking.com"
        if neighborhood:
            query = f"top luxury 5-star hotels in {city} near {neighborhood} room rates nightly price 2026"
    else:
        query = f"top recommended best value 3-star 4-star mid-range hotels in {city} room rates nightly price per night 2026 booking.com"
        if neighborhood:
            query = f"top recommended mid-range hotels in {city} near {neighborhood} room rates nightly price 2026 booking.com"

    try:
        response = client.search(
            query=query,
            max_results=6,
            include_answer=True,
            search_depth="basic"
        )
        
        answer = response.get("answer", "")
        raw_results = response.get("results", [])
        
        formatted_results = []
        for r in raw_results:
            formatted_results.append({
                "title": r.get("title", "Unknown"),
                "url": r.get("url", ""),
                "content": r.get("content", "").strip()
            })

        # City-wide exploration links tailored to tier
        encoded_term = urllib.parse.quote_plus(f"{city} hostels" if is_budget_or_hostel else f"{city} hotels")
        city_links = {
            "google_hotels": f"https://www.google.com/travel/hotels?q={encoded_term}",
            "booking_com": f"https://www.booking.com/searchresults.html?ss={encoded_term}"
        }

        return {
            "query": query,
            "answer": answer,
            "raw_results": formatted_results,
            "city_links": city_links
        }
    except Exception as e:
        return {
            "error": str(e),
            "answer": f"Error performing hotel search for {city}: {str(e)}",
            "raw_results": [],
            "city_links": {}
        }
