import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

def flight_search(departure_iata: str, arrival_iata: str, date: str | None = None, currency: str = "INR") -> str:
    """
    Searches live Google Flights data using fast-flights (primary engine),
    with automatic fallback to SerpApi Google Flights if configured.
    
    Args:
        departure_iata: 3-letter IATA code (e.g. 'DEL', 'BOM', 'JFK').
        arrival_iata: 3-letter IATA code (e.g. 'HND', 'CDG', 'LHR').
        date: Travel date in 'YYYY-MM-DD' format. If None, defaults to ~30 days from now.
        currency: Currency code, defaults to 'INR'.
    """
    dep = departure_iata.strip().upper()
    arr = arrival_iata.strip().upper()

    # If no date is given, target ~30 days in the future
    if not date:
        date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    else:
        # Validate date format, fallback to default if malformed
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    # --- PRIMARY ENGINE: fast-flights (Direct Google Flights) ---
    try:
        from fast_flights import FlightQuery, create_query, get_flights

        query = create_query(
            flights=[FlightQuery(date=date, from_airport=dep, to_airport=arr)],
            trip="one-way",
            currency=currency
        )
        results = get_flights(query)

        if results and len(results) > 0:
            formatted_flights = []
            prices = []
            selected_flights = []
            seen_combos = set()

            for f in results:
                airlines_str = ", ".join(f.airlines) if f.airlines else "Unknown Airline"
                arr_dest = getattr(f.flights[-1].to_airport, "code", arr) if getattr(f, "flights", None) else arr
                price_val = getattr(f, "price", None)
                combo_key = (airlines_str, arr_dest, price_val)
                if combo_key not in seen_combos:
                    seen_combos.add(combo_key)
                    selected_flights.append(f)
                if len(selected_flights) >= 6:
                    break

            # Fallback to first flights if deduplication yielded none
            if not selected_flights:
                selected_flights = results[:6]

            for idx, f in enumerate(selected_flights, 1):
                airlines = ", ".join(f.airlines) if f.airlines else "Unknown Airline"
                price_val = getattr(f, "price", None)
                
                if price_val:
                    prices.append(price_val)
                    price_str = f"₹{price_val:,}" if currency == "INR" else f"${price_val}"
                else:
                    price_str = "Price unavailable"

                # Extract leg details
                flights_list = getattr(f, "flights", [])
                stops = max(0, len(flights_list) - 1)
                
                if flights_list:
                    first_leg = flights_list[0]
                    last_leg = flights_list[-1]
                    dep_time = f"{first_leg.departure.time[0]:02d}:{first_leg.departure.time[1]:02d}"
                    arr_time = f"{last_leg.arrival.time[0]:02d}:{last_leg.arrival.time[1]:02d}"
                    dep_code = getattr(first_leg.from_airport, "code", dep)
                    arr_code = getattr(last_leg.to_airport, "code", arr)
                    duration_mins = sum(getattr(leg, "duration", 0) for leg in flights_list)
                    dur_str = f"{duration_mins // 60}h {duration_mins % 60}m" if duration_mins else "N/A"
                else:
                    dep_time = "N/A"
                    arr_time = "N/A"
                    dep_code = dep
                    arr_code = arr
                    dur_str = "N/A"

                formatted_flights.append(
                    f"{idx}. **{airlines}**\n"
                    f"   Route: {dep_code} ({dep_time}) -> {arr_code} ({arr_time})\n"
                    f"   Duration: {dur_str} | Stops: {stops}\n"
                    f"   Price: **{price_str}** per passenger (Economy)"
                )

            header = f"### ✈️ Live Google Flights Options: {dep} -> {arr} (Date: {date})\n\n"
            avg_note = ""
            if prices:
                avg_fare = sum(prices) // len(prices)
                round_trip_est = avg_fare * 2
                avg_note = (
                    f"\n\n💰 **Estimated Flight Benchmark:**\n"
                    f"- Average One-Way: **₹{avg_fare:,}** ($ {avg_fare // 85})\n"
                    f"- Estimated Round-Trip: **₹{round_trip_est:,}** ($ {round_trip_est // 85})"
                )

            return header + "\n\n".join(formatted_flights) + avg_note

    except Exception as primary_error:
        print(f"fast-flights engine notice: {primary_error}. Attempting fallback...")

    # --- FALLBACK ENGINE: SerpApi Google Flights ---
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if serpapi_key:
        try:
            from backend.tools.serpapi_flight_tool import serpapi_flight_search
        except ImportError:
            from tools.serpapi_flight_tool import serpapi_flight_search
        except Exception as serp_err:
            print(f"SerpApi fallback error: {serp_err}")
            return f"Unable to retrieve live Google Flights for route {dep} -> {arr} on {date}."
        return serpapi_flight_search(departure_iata=dep, arrival_iata=arr, date=date, currency=currency)

    return f"Unable to retrieve live Google Flights for route {dep} -> {arr} on {date}. Please verify the route or date."