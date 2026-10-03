import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

def serpapi_flight_search(departure_iata: str, arrival_iata: str, date: str | None = None, currency: str = "INR") -> str:
    """
    Fallback flight search tool using SerpApi's Google Flights engine.
    Requires SERPAPI_API_KEY in .env.
    """
    if not SERPAPI_API_KEY:
        return "SerpApi API key not found. Please set SERPAPI_API_KEY in .env to use SerpApi fallback."
    
    try:
        from serpapi import GoogleSearch
    except ImportError:
        return "serpapi library is not installed. Run `pip install google-search-results`."

    dep = departure_iata.strip().upper()
    arr = arrival_iata.strip().upper()

    if not date:
        date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    params = {
        "engine": "google_flights",
        "departure_id": dep,
        "arrival_id": arr,
        "outbound_date": date,
        "currency": currency,
        "api_key": SERPAPI_API_KEY,
        "hl": "en"
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
    except Exception as e:
        return f"SerpApi connection error: {str(e)}"

    flights_list = results.get("best_flights", []) + results.get("other_flights", [])
    if not flights_list:
        return f"No Google Flights found via SerpApi for {dep} -> {arr} on {date}."

    formatted_flights = []
    prices = []

    for idx, f in enumerate(flights_list[:5], 1):
        price = f.get("price")
        if price:
            prices.append(price)
            price_str = f"₹{price:,}" if currency == "INR" else f"${price}"
        else:
            price_str = "Price unavailable"

        duration = f.get("total_duration", "N/A")
        flights_info = f.get("flights", [])
        
        airlines = set()
        flight_nums = []
        dep_time = "N/A"
        arr_time = "N/A"

        for segment in flights_info:
            airline_name = segment.get("airline")
            if airline_name:
                airlines.add(airline_name)
            fn = segment.get("flight_number")
            if fn:
                flight_nums.append(fn)
            if dep_time == "N/A":
                dep_time = segment.get("departure_airport", {}).get("time", "N/A")
            arr_time = segment.get("arrival_airport", {}).get("time", "N/A")

        airline_str = ", ".join(airlines) if airlines else "Unknown Airline"
        flight_num_str = f" ({', '.join(flight_nums)})" if flight_nums else ""
        stops = len(flights_info) - 1

        formatted_flights.append(
            f"{idx}. {airline_str}{flight_num_str}\n"
            f"   Route: {dep} ({dep_time}) -> {arr} ({arr_time})\n"
            f"   Duration: {duration} mins | Stops: {stops}\n"
            f"   Price: {price_str} per passenger"
        )

    avg_price_note = ""
    if prices:
        avg = sum(prices) // len(prices)
        avg_price_note = f"\n\n💰 **Average One-Way Flight Fare:** ₹{avg:,} per passenger" if currency == "INR" else f"\n\n💰 **Average One-Way Flight Fare:** ${avg} per passenger"

    return "\n\n".join(formatted_flights) + avg_price_note
