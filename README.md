# 🌍 TravelPlanner: Autonomous Multi-AI Agent System

An autonomous, multi-agent travel planning system built with **LangGraph**, **Hugging Face (`meta-llama/Llama-3.3-70B-Instruct`)**, **Groq**, **Tavily**, and **PostgreSQL Persistence**. 

The system takes natural language travel requests (e.g., *"Plan a 7-day trip from Delhi to Tokyo and Kyoto in July on a mid budget"*) and orchestrates 5 specialized AI agents to analyze climates, recommend optimal travel dates, discover live flights, find vetted accommodations with verified booking links, curate sights & dining (including vegetarian/Indian friendly options), and construct an exhaustive day-by-day master itinerary with a complete financial ledger.

---

## 🏗️ Multi-Agent Architecture & Flow

```mermaid
flowchart TD
    User([👤 User Request via UI / CLI]) --> StartNode[START]
    StartNode --> WeatherAgent[🌤️ 1. Weather & Climate Agent]
    WeatherAgent --> FlightAgent[✈️ 2. Flight Discovery Agent]
    FlightAgent --> HotelAgent[🏨 3. Hotel Discovery Agent]
    HotelAgent --> PlacesAgent[🏛️ 4. Attractions & Dining Agent]
    PlacesAgent --> ItineraryAgent[🗺️ 5. Master Itinerary & Budget Agent]
    ItineraryAgent --> EndNode[END]

    subgraph StatePersistence ["💾 PostgreSQL Persistence (PostgresSaver)"]
        WeatherAgent -.-> DB[(PostgreSQL: travel_planner)]
        FlightAgent -.-> DB
        HotelAgent -.-> DB
        PlacesAgent -.-> DB
        ItineraryAgent -.-> DB
    end
```

---

## 🧠 Shared State Schema (`TravelState`)

All agents communicate through an immutable, versioned state dictionary called `TravelState`. As each agent completes its task, it writes its findings into this shared state:

```python
class TravelState(TypedDict):
    message: Annotated[list[AnyMessage], operator.add]  # Append-only conversation history
    user_query: str                                    # Original user prompt
    destination: str                                   # Visited cities (e.g. "Tokyo, Kyoto")
    duration_days: int                                 # Trip duration (e.g. 5, 7, 10)
    travel_date: str                                   # Optimal travel start date (e.g. "2027-07-22")
    weather_results: str                               # Climate facts & recommended dates
    flight_results: str                                # Live flights & route pricing details
    hotel_results: str                                 # Accommodations & verified booking links
    places_results: str                                # Sights, activities & dining options
    itinerary: str                                     # Final day-by-day plan & budget ledger
    llm_calls: int                                     # Cumulative LLM invocation count
```

---

## 🤖 Detailed Working of Each Agent

### 1. 🌤️ Weather & Climate Agent (`agents/weather_agent.py`)
- **Execution Order:** Runs **FIRST** (`START -> weather_agent`).
- **Core Purpose:** Analyzes historical ERA5 climate data and live forecasts to recommend the **optimal 7-day travel window** (minimizing rain and extreme heat) and sets `travel_date` for downstream flight and hotel pricing.
- **Tools:** Open-Meteo Geocoding & ERA5 Historical Archive ([`tools/weather_tool.py`](tools/weather_tool.py), no API key needed).

### 2. ✈️ Flight Discovery Agent (`agents/flight_agent.py`)
- **Execution Order:** Runs **SECOND** (`weather_agent -> flight_agent`).
- **Core Purpose:** Maps cities to official IATA airport/metropolitan codes (e.g., Delhi $\to$ `DEL`, Tokyo $\to$ `TYO`) and discovers live commercial flights on Google Flights for the exact recommended date.
- **Tools:** `fast-flights` Google Flights scraper ([`tools/flight_tool.py`](tools/flight_tool.py)) with SerpApi fallback ([`tools/serpapi_flight_tool.py`](tools/serpapi_flight_tool.py)).
- **Output:** Selects up to 6 diverse airline options across price, duration, and carrier type with realistic round-trip budget benchmarks.

### 3. 🏨 Hotel & Lodging Discovery Agent (`agents/hotel_agent.py`)
- **Execution Order:** Runs **THIRD** (`flight_agent -> hotel_agent`).
- **Core Purpose:** Multi-city aware lodging agent. Allocates trip nights across visited cities (e.g., 4 nights Tokyo + 3 nights Kyoto for a 7-day trip), performs live Tavily searches for each city matching the traveler's semantic budget tier (*budget*, *mid-range*, *luxury*, *balanced*), and calculates exact room rates and total stay costs.
- **Direct Property Booking Links:** Uses [`generate_hotel_booking_links()`](tools/hotel_tool.py) to construct verified, direct search links to Google Hotels and Booking.com **exclusively for the hotels discovered in the search**.
- **Live Internet Currency Conversion:** Connects to [`tools/currency_tool.py`](tools/currency_tool.py) for real-time European Central Bank foreign exchange rates (`USD -> INR`).

### 4. 🏛️ Attractions & Dining Agent (`agents/places_agent.py`)
- **Execution Order:** Runs **FOURTH** (`hotel_agent -> places_agent`).
- **Core Purpose:** Multi-city aware sightseeing and dining curation scaled to the exact days spent in each city.
- **Key Features:**
  - **Zone-Clustered Sights:** Groups attractions by neighborhood to minimize intra-city commute time, complete with typical visit duration and entry fees (in USD & INR).
  - **Regional Specialties & Indian/Vegetarian Dining:** Identifies authentic local foods and curates recommended vegetarian-friendly and Indian restaurants with average meal costs per person.
  - **Local Transit Advice:** Recommends regional transit passes (Tokyo Subway 72hr Ticket, Suica, ICOCA, Kyoto Bus Pass).
  - **Google Maps Discovery Links:** Direct navigation links for attractions and dining.

### 5. 🗺️ Master Itinerary & Financial Ledger Agent (`agents/itinerary_agent.py`)
- **Execution Order:** Runs **FIFTH** (`places_agent -> itinerary_agent -> END`).
- **Core Purpose:** The synthesis brain that weaves all intelligence into an all-in-one day-by-day travel plan and comprehensive budget breakdown.
- **Key Deliverables:**
  1. **Trip Snapshot:** Pacing, theme, and key booked accommodations.
  2. **Day-by-Day Master Schedule (Day 1 to Day $N$):** Morning, afternoon, and evening breakdowns with specific meals, transit tips, and inter-city bullet train transfers.
  3. **Comprehensive Financial Ledger:** Clean breakdown covering Flights, Hotels, Local Transit, Sightseeing, Dining, and a 10% contingency buffer with Grand Total trip cost in both INR and USD.
  4. **Pre-Trip Checklist & Practical Advice:** Essential visa requirements, eSIM/Pocket WiFi, Forex card/cash guidance, cultural etiquette, and weather-tailored packing essentials.

---

## 💾 PostgreSQL Persistence & Session Memory

The application uses **`langgraph-checkpoint-postgres`** with a thread-safe **`psycopg_pool.ConnectionPool`** to persist all sessions.

```
PostgreSQL Database: travel_planner
├── checkpoints          # Master registry of state snapshots keyed by thread_id
├── checkpoint_blobs    # Serialized binary data (flight results, messages, state)
├── checkpoint_writes   # Step-by-step transaction journal between nodes
└── checkpoint_migrations # Internal schema version management
```

### Why this matters:
- **Zero Data Loss:** If the server restarts or crashes, all conversation history and travel findings remain safe in PostgreSQL.
- **Multi-Turn Continuity:** When a user returns after days or weeks, simply passing their `thread_id` restores their entire state via `app.get_state({"configurable": {"thread_id": user_id}})`.
- **Thread-Safe Pooling:** `ConnectionPool(max_size=20, kwargs={"autocommit": True})` ensures multiple users can plan trips concurrently in the UI without database connection bottlenecks.

---

## 📁 Project Directory Structure

```text
TravelPlanner/
├── backend/
│   ├── __init__.py
│   ├── main.py                     # StateGraph definition, PostgreSQL pooling & graph entrypoints
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── weather_agent.py        # Node 1: Weather & climate intelligence (OSM Nominatim dynamic geocoding)
│   │   ├── flight_agent.py         # Node 2: Google Flights discovery & live pricing
│   │   ├── hotel_agent.py          # Node 3: Multi-city hotel discovery & verified booking links
│   │   ├── places_agent.py         # Node 4: Attractions, authentic web photos, local food & dining
│   │   └── itinerary_agent.py      # Node 5: Day-by-day master itinerary, embedded photos & financial ledger
│   └── tools/
│       ├── __init__.py
│       ├── llm_provider.py         # Codecrafter LLM provider (gpt-5.6-luna) with fallbacks
│       ├── weather_tool.py         # OSM Geocoding, Forecast & ERA5 Climate API
│       ├── flight_tool.py          # fast-flights Google Flights scraper & deduplication
│       ├── serpapi_flight_tool.py  # SerpApi Google Flights standby fallback
│       ├── hotel_tool.py           # Tavily hotel search & deep booking links generator
│       ├── places_tool.py          # Tavily + Wikipedia attraction search & live web image fetching
│       ├── currency_tool.py        # Live ECB / open.er-api real-time currency conversion
│       └── tavily_tool.py          # General Tavily search wrapper
├── frontend/
│   ├── __init__.py
│   └── app.py                      # Interactive Streamlit UI with multi-agent tracker & photo galleries
├── main.py                         # Root entrypoint wrapper (forwards to backend.main)
├── app.py                          # Root Streamlit wrapper (forwards to frontend.app)
├── test_e2e.py                     # Automated end-to-end multi-agent verification script
├── requirements.txt                # Project dependencies
├── .env                            # API keys and DATABASE_URL
└── DATABASE_GUIDE.md               # PostgreSQL checkpointer reference documentation
```

---

## 🚀 Getting Started

### 1. Installation
Clone the repository and install dependencies in your virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Variables (`.env`)
Create a `.env` file in the root directory:

```env
# LLM Providers (Codecrafter prioritized)
CODECRAFTER_API_KEY=your_codecrafter_key
GROQ_API_KEY=your_groq_api_key
HF_TOKEN=your_huggingface_token

# Tools
TAVILY_API_KEY=your_tavily_api_key
SERPAPI_API_KEY=your_serpapi_key_optional

# PostgreSQL Connection (URL-encode special characters in password, e.g. @ -> %40)
DATABASE_URL=postgresql://postgres:YourPassword%40123@localhost:5432/travel_planner

# Session Security
AUTH_SECRET_KEY=your_auth_secret_key
```

*(Note: Open-Meteo weather, OpenStreetMap geocoding, and ECB currency APIs require no keys).*

### 🔒 Authentication, Authorization & 30-Day Browser Storage
The platform includes built-in authentication and session persistence:
- **Email & Password Authentication**: Passwords hashed using PBKDF2-HMAC-SHA256 with 200,000 rounds and cryptographic salts, stored in PostgreSQL's `users` table (with automatic SQLite fallback).
- **30-Day Browser Local Storage**: Once signed in, a signed, tamper-proof session token is stored in the browser's `localStorage`. Opening or refreshing the app automatically restores the user session without re-prompting for credentials.
- **Trip Isolation & Authorization**: Saved trips in PostgreSQL are partitioned by user ID (`user_{user_id}_{thread_id}`). Users can only inspect, load, and manage their own itineraries.

### 3. Launching the Frontend UI
Run the interactive Streamlit user interface:

```bash
streamlit run frontend/app.py
```
*(Or run `streamlit run app.py` via the root wrapper).*

### 4. Running Backend / Tests Directly
To run the backend pipeline directly via CLI:

```bash
python backend/main.py
# or run the complete end-to-end test suite
python test_e2e.py
```

### 5. Integration with Custom Services
When integrating backend agents into any API or frontend:

```python
from backend.main import run_travel_planner, stream_travel_planner

# Full invocation
state = run_travel_planner("Plan a trip of 3 days to Goa on a mid budget", thread_id="user_session_42")
print(state["weather_results"])
print(state["flight_results"])
print(state["hotel_results"])
print(state["places_results"])
print(state["itinerary"])

# Real-time event streaming for UI spinners / step-by-step progress
for event in stream_travel_planner("Plan a 3 day trip to Goa", thread_id="user_session_42"):
    print(event)
```
