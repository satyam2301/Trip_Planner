import os
import sys
from pathlib import Path
import atexit
from typing import TypedDict, Annotated
import operator

# Ensure root and backend directories are on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")
load_dotenv()

from langgraph.graph import StateGraph, START, END
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
)
from langchain_groq import ChatGroq

try:
    from backend.tools.tavily_tool import tavily_search
    from backend.agents.weather_agent import weather_agent_node
    from backend.agents.flight_agent import flight_agent_node
    from backend.agents.hotel_agent import hotel_agent_node
    from backend.agents.places_agent import places_agent_node
    from backend.agents.itinerary_agent import itinerary_agent_node
except ImportError:
    from tools.tavily_tool import tavily_search
    from agents.weather_agent import weather_agent_node
    from agents.flight_agent import flight_agent_node
    from agents.hotel_agent import hotel_agent_node
    from agents.places_agent import places_agent_node
    from agents.itinerary_agent import itinerary_agent_node

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")

# Graph State Definition
class TravelState(TypedDict, total=False):
    message: Annotated[list[AnyMessage], operator.add]
    user_query: str
    destination: str
    duration_days: int
    travel_date: str
    weather_results: str
    flight_results: str
    hotel_results: str
    places_results: str
    itinerary: str
    place_images: list[dict]
    llm_calls: int

# Build the Graph
builder = StateGraph(TravelState)

# Add Nodes
builder.add_node("weather_agent", weather_agent_node)
builder.add_node("flight_agent", flight_agent_node)
builder.add_node("hotel_agent", hotel_agent_node)
builder.add_node("places_agent", places_agent_node)
builder.add_node("itinerary_agent", itinerary_agent_node)

# Define Flow: Weather -> Flight -> Hotel -> Places -> Itinerary -> END
builder.add_edge(START, "weather_agent")
builder.add_edge("weather_agent", "flight_agent")
builder.add_edge("flight_agent", "hotel_agent")
builder.add_edge("hotel_agent", "places_agent")
builder.add_edge("places_agent", "itinerary_agent")
builder.add_edge("itinerary_agent", END)

# Checkpointer setup: PostgreSQL with automatic graceful fallback to MemorySaver
checkpointer = None
try:
    if DATABASE_URL and "localhost" not in DATABASE_URL or os.getenv("TEST_DB", "true") == "true":
        pool = ConnectionPool(
            conninfo=DATABASE_URL,
            max_size=20,
            kwargs={"autocommit": True}
        )
        atexit.register(pool.close)
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()
except Exception as e:
    checkpointer = None

if checkpointer is None:
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()

# Compile the runnable graph with persistence
app = builder.compile(checkpointer=checkpointer)

def run_travel_planner(user_query: str, thread_id: str = "default_session") -> TravelState:
    """
    Entrypoint to run the travel planning graph for a given user query.
    Can be imported and called directly from Streamlit, FastAPI, or any UI.
    
    Args:
        user_query: The travel prompt entered by the user.
        thread_id: A unique session/conversation ID for state persistence in PostgreSQL.
        
    Returns:
        The final updated TravelState.
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_input: TravelState = {
        "message": [HumanMessage(content=user_query)],
        "user_query": user_query,
        "destination": "",
        "duration_days": 7,
        "travel_date": "",
        "weather_results": "",
        "flight_results": "",
        "hotel_results": "",
        "places_results": "",
        "itinerary": "",
        "llm_calls": 0,
    }
    
    final_state = app.invoke(initial_input, config=config)
    return final_state

def stream_travel_planner(user_query: str, thread_id: str = "default_session"):
    """
    Generator entrypoint to stream state updates node-by-node to the UI.
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_input: TravelState = {
        "message": [HumanMessage(content=user_query)],
        "user_query": user_query,
        "destination": "",
        "duration_days": 7,
        "travel_date": "",
        "weather_results": "",
        "flight_results": "",
        "hotel_results": "",
        "places_results": "",
        "itinerary": "",
        "llm_calls": 0,
    }
    
    for event in app.stream(initial_input, config=config):
        yield event

if __name__ == "__main__":
    sample_query = "Plan a 7 day trip from Delhi to Japan in July on a mid budget"
    session_id = "user_trip_japan_july"
    print(f"Running planner for: '{sample_query}' with thread_id='{session_id}'...\n")
    
    result = run_travel_planner(sample_query, thread_id=session_id)
    
    print("\n" + "=" * 60)
    print("--- Final TravelState (Saved to PostgreSQL) ---")
    print(f"User Query: {result.get('user_query')}")
    print(f"Destination: {result.get('destination')}")
    print(f"Total LLM Calls: {result.get('llm_calls')}")
    print(f"\n🌤️ Weather & Best Window Results:\n{result.get('weather_results')}")
    print(f"\n✈️ Flight Results:\n{result.get('flight_results')}")
    print(f"\n🏨 Hotel Results:\n{result.get('hotel_results')}")
    print(f"\n🏛️ Attractions & Dining Results:\n{result.get('places_results')}")
    print(f"\n🗺️ Master Itinerary & Financial Ledger:\n{result.get('itinerary')}")
    print("=" * 60 + "\n")