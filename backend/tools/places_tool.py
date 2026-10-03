import os
import urllib.parse
from typing import Optional
import requests
from dotenv import load_dotenv
from tavily import TavilyClient

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# In-memory image cache for fast lookups
_IMAGE_CACHE: dict[str, str] = {}


def fetch_place_image(place_name: str, city: str = "") -> str | None:
    """
    Fetches a real web image URL for a landmark, beach, or attraction.
    1. Queries Tavily with include_images=True for authentic web photos.
    2. Falls back to Wikipedia pageimage thumbnail API.
    """
    if not place_name or not place_name.strip():
        return None

    clean_place = place_name.strip()
    cache_key = f"{clean_place.lower()}_{city.lower().strip()}"
    if cache_key in _IMAGE_CACHE:
        return _IMAGE_CACHE[cache_key]

    # Priority 1: Tavily Image Search
    if TAVILY_API_KEY:
        try:
            client = TavilyClient(api_key=TAVILY_API_KEY)
            query = f"{clean_place} {city} tourist attraction landmark" if city else f"{clean_place} tourist attraction"
            res = client.search(query=query, include_images=True, max_results=2)
            imgs = res.get("images", [])
            for img in imgs:
                if isinstance(img, str) and (img.startswith("http://") or img.startswith("https://")):
                    _IMAGE_CACHE[cache_key] = img
                    return img
        except Exception as e:
            print(f"Tavily image fetch error for '{clean_place}': {e}")

    # Priority 2: Wikipedia Thumbnail API Fallback
    try:
        headers = {"User-Agent": "TravelPlannerApp/1.0 (travel-planner-agent)"}
        url = f"https://en.wikipedia.org/w/api.php?action=query&titles={requests.utils.quote(clean_place)}&prop=pageimages&format=json&pithumbsize=600"
        resp = requests.get(url, headers=headers, timeout=4).json()
        pages = resp.get("query", {}).get("pages", {})
        for _, page in pages.items():
            if "thumbnail" in page and "source" in page["thumbnail"]:
                img_url = page["thumbnail"]["source"]
                _IMAGE_CACHE[cache_key] = img_url
                return img_url
    except Exception as e:
        print(f"Wikipedia image fetch error for '{clean_place}': {e}")

    return None


from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_attraction_images(attractions: list[str], city: str = "") -> list[dict]:
    """
    Fetches real web photos for a list of attractions in parallel using ThreadPoolExecutor.
    Limits to top 4 attractions to ensure lightning fast response times (< 5s).
    """
    if not attractions:
        return []

    target_attractions = [a.strip() for a in attractions[:4] if a and len(a.strip()) >= 3]
    if not target_attractions:
        return []

    results = []
    seen_urls = set()

    def _worker(attr: str):
        return attr, fetch_place_image(attr, city)

    with ThreadPoolExecutor(max_workers=min(4, len(target_attractions))) as executor:
        futures = [executor.submit(_worker, a) for a in target_attractions]
        for f in as_completed(futures):
            try:
                attr, url = f.result()
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    results.append({
                        "name": attr,
                        "city": city,
                        "url": url
                    })
            except Exception as e:
                print(f"Error fetching image for '{attr}': {e}")

    return results


def places_search(
    city: str,
    days: int = 3,
    interests: Optional[str] = None,
    dietary_preference: Optional[str] = None
) -> dict:
    """
    Discovers top attractions, sightseeing experiences, and dining options
    (including local specialties and vegetarian/Indian options) for a city
    using targeted Tavily searches scaled to the number of days spent.
    
    Args:
        city: City name (e.g., 'Tokyo', 'Kyoto', 'Goa')
        days: Number of days staying in this city
        interests: User preferences (e.g., 'temples', 'beaches', 'nature')
        dietary_preference: Food preferences (e.g., 'vegetarian', 'jain', 'halal')
        
    Returns:
        dict containing attraction findings, dining findings, Google Maps discovery links, and web photos.
    """
    if not TAVILY_API_KEY:
        return {
            "city": city,
            "days": days,
            "attractions_summary": "Tavily API key not found.",
            "attractions_raw": [],
            "dining_summary": "Tavily API key not found.",
            "dining_raw": [],
            "images": [],
            "maps_links": {}
        }

    client = TavilyClient(api_key=TAVILY_API_KEY)

    # 1. Search Attractions scaled to number of days with images enabled
    interest_suffix = f"focusing on {interests}" if interests else "must visit iconic sights and hidden gems"
    attractions_query = f"top attractions things to do in {city} for {days} days {interest_suffix} entry ticket price timing 2026"
    
    # 2. Search Food & Dining tailored for local specialties + vegetarian/Indian friendly options
    diet_str = f"{dietary_preference} and Indian restaurants" if dietary_preference else "local food specialties plus popular vegetarian Indian friendly dining"
    dining_query = f"must try famous local food dishes and top restaurants in {city} {diet_str} 2026"

    attractions_res = {"answer": "", "results": [], "images": []}
    dining_res = {"answer": "", "results": []}

    try:
        attractions_res = client.search(
            query=attractions_query,
            max_results=5,
            include_answer=True,
            include_images=True,
            search_depth="basic"
        )
    except Exception as e:
        attractions_res = {"answer": f"Could not fetch attractions: {e}", "results": [], "images": []}

    try:
        dining_res = client.search(
            query=dining_query,
            max_results=5,
            include_answer=True,
            search_depth="basic"
        )
    except Exception as e:
        dining_res = {"answer": f"Could not fetch dining recommendations: {e}", "results": []}

    encoded_city = urllib.parse.quote_plus(city)
    maps_links = {
        "attractions_map": f"https://www.google.com/maps/search/?api=1&query={encoded_city}+top+attractions",
        "restaurants_map": f"https://www.google.com/maps/search/?api=1&query={encoded_city}+best+restaurants"
    }

    return {
        "city": city,
        "days": days,
        "attractions_summary": attractions_res.get("answer", ""),
        "attractions_raw": attractions_res.get("results", []),
        "images": [img for img in attractions_res.get("images", []) if isinstance(img, str) and img.startswith("http")],
        "dining_summary": dining_res.get("answer", ""),
        "dining_raw": dining_res.get("results", []),
        "maps_links": maps_links
    }
