import calendar
from datetime import datetime
import requests

WMO_WEATHER_CODES = {
    0: "Clear sky ☀️",
    1: "Mainly clear 🌤️",
    2: "Partly cloudy ⛅",
    3: "Overcast ☁️",
    45: "Fog 🌫️",
    48: "Depositing rime fog 🌫️",
    51: "Light drizzle 🌦️",
    53: "Moderate drizzle 🌦️",
    55: "Dense drizzle 🌧️",
    61: "Slight rain 🌧️",
    63: "Moderate rain 🌧️",
    65: "Heavy rain ⛈️",
    71: "Slight snow 🌨️",
    73: "Moderate snow 🌨️",
    75: "Heavy snow ❄️",
    80: "Slight rain showers 🌦️",
    81: "Moderate rain showers 🌧️",
    82: "Violent rain showers ⛈️",
    95: "Thunderstorm ⚡",
}

# Session in-memory cache to prevent redundant API queries for the same destination
_GEOCODE_CACHE: dict[str, tuple[float, float, str]] = {}

def geocode_city(city_name: str) -> tuple[float, float, str] | None:
    """
    Dynamically resolves coordinates (latitude, longitude, formatted place name)
    for any city, tourist region, state, or island via live Geocoding APIs.
    
    1. Checks in-memory cache.
    2. Primary Geocoder: OpenStreetMap Nominatim API (natively supports states,
       regions, islands, cities, and landmarks worldwide without hardcoding).
    3. Fallback Geocoder: Open-Meteo Geocoding API with strict exact-match verification.
    """
    if not city_name or not city_name.strip():
        return None

    clean_name = city_name.strip()
    norm = clean_name.lower()
    for prefix in ["trip to ", "visit to ", "travel to ", "tour to ", "flights to ", "vacation in ", "hotels in "]:
        if norm.startswith(prefix):
            clean_name = clean_name[len(prefix):].strip()
            norm = clean_name.lower()

    # Check cache
    if norm in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[norm]

    # Primary API: OpenStreetMap Nominatim
    try:
        headers = {"User-Agent": "TravelPlannerApp/1.0 (travel-planner-agent)"}
        nom_url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(clean_name)}&format=json&limit=1&accept-language=en"
        resp = requests.get(nom_url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if data and len(data) > 0:
                match = data[0]
                lat = float(match["lat"])
                lon = float(match["lon"])
                display_name = match.get("display_name", clean_name)
                parts = [p.strip() for p in display_name.split(",")]
                formatted_name = f"{parts[0]}, {parts[-1]}" if len(parts) >= 2 else display_name
                result = (lat, lon, formatted_name)
                _GEOCODE_CACHE[norm] = result
                return result
    except Exception as e:
        print(f"Nominatim geocoding error for '{clean_name}': {e}")

    # Fallback API: Open-Meteo with strict exact-name filtering
    try:
        primary_part = clean_name.split(",")[0].strip()
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={requests.utils.quote(primary_part)}&count=10&language=en&format=json"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            # Priority A: Exact name match (case-insensitive)
            for r in results:
                if r.get("name", "").lower() == primary_part.lower():
                    c_name = r.get("name", primary_part)
                    country = r.get("country", "")
                    result = (r["latitude"], r["longitude"], f"{c_name}, {country}".strip(", "))
                    _GEOCODE_CACHE[norm] = result
                    return result
            # Priority B: Admin1 (state/province) exact match
            for r in results:
                if (r.get("admin1") or "").lower() == primary_part.lower():
                    c_name = r.get("name", primary_part)
                    country = r.get("country", "")
                    result = (r["latitude"], r["longitude"], f"{c_name}, {r.get('admin1')}, {country}".strip(", "))
                    _GEOCODE_CACHE[norm] = result
                    return result
    except Exception as e:
        print(f"Open-Meteo fallback geocoding error for '{clean_name}': {e}")

    return None

def get_live_forecast(latitude: float, longitude: float, days: int = 14) -> str:
    """
    Fetches up to 14 days of live daily weather forecast.
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode"
        f"&timezone=auto&forecast_days={min(days, 16)}"
    )
    try:
        response = requests.get(url, timeout=10)
        daily = response.json().get("daily", {})
        times = daily.get("time", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])
        codes = daily.get("weathercode", [])
        
        lines = ["### Live Weather Forecast (Next 14 Days):"]
        lines.append("| Date | Max Temp (°C) | Min Temp (°C) | Rain (mm) | Condition |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")
        
        for i in range(len(times)):
            condition = WMO_WEATHER_CODES.get(codes[i], "Variable")
            lines.append(f"| {times[i]} | {tmax[i]}°C | {tmin[i]}°C | {precip[i]} mm | {condition} |")
            
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching live forecast: {e}"

def get_historical_climate(latitude: float, longitude: float, month: int, year: int = 2025) -> str:
    """
    Fetches historical climate data for a specific month from the Open-Meteo ERA5 archive
    and computes weekly averages to find the best 7-day travel window.
    """
    month_name = calendar.month_name[month]
    num_days = calendar.monthrange(year, month)[1]
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{num_days:02d}"
    
    url = (
        f"https://archive-api.open-meteo.com/v1/archive?latitude={latitude}&longitude={longitude}"
        f"&start_date={start_date}&end_date={end_date}"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        f"&timezone=auto"
    )
    try:
        response = requests.get(url, timeout=10)
        daily = response.json().get("daily", {})
        times = daily.get("time", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        rain = daily.get("precipitation_sum", [])
        
        if not times:
            return f"No historical climate data available for {month_name}."
            
        avg_max = sum(tmax) / len(tmax)
        avg_min = sum(tmin) / len(tmin)
        total_rain = sum(rain)
        rainy_days = sum(1 for r in rain if r > 1.0)
        
        summary = [
            f"### Climate Analysis for {month_name}:",
            f"- **Average Daytime High:** {avg_max:.1f}°C",
            f"- **Average Nighttime Low:** {avg_min:.1f}°C",
            f"- **Total Monthly Rainfall:** {total_rain:.1f} mm across {rainy_days} rainy days",
            "\n#### Weekly Breakdown (To determine best 7-day window):",
            "| Period | Window Dates | Avg High (°C) | Avg Low (°C) | Total Rain (mm) |",
            "| :--- | :--- | :---: | :---: | :---: |"
        ]
        
        # Calculate 4 distinct 7-day blocks
        for w in range(4):
            s_idx = w * 7
            e_idx = s_idx + 7
            window_dates = f"{times[s_idx]} to {times[e_idx - 1]}"
            w_max = sum(tmax[s_idx:e_idx]) / 7
            w_min = sum(tmin[s_idx:e_idx]) / 7
            w_rain = sum(rain[s_idx:e_idx])
            summary.append(f"| Week {w + 1} | {window_dates} | {w_max:.1f}°C | {w_min:.1f}°C | {w_rain:.1f} mm |")
            
        return "\n".join(summary)
    except Exception as e:
        return f"Error fetching historical climate for {month_name}: {e}"

def weather_search(city: str, month: int | None = None, is_upcoming: bool = True) -> str:
    """
    Main tool function to get either live forecast (for upcoming trips) or historical climate analysis.
    """
    geo = geocode_city(city)
    if not geo:
        return f"Could not find coordinates for '{city}'. Please verify city name."
    
    lat, lon, place_name = geo
    
    if is_upcoming or month is None:
        forecast_info = get_live_forecast(lat, lon)
        return f"**Weather Report for {place_name}:**\n\n{forecast_info}"
    else:
        climate_info = get_historical_climate(lat, lon, month=month)
        return f"**Historical Climate Profile for {place_name}:**\n\n{climate_info}"
