"""
Travel Planner - Root Entrypoint Wrapper.
The core multi-agent graph logic is segregated in `backend/main.py`.
"""
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.main import (
    app,
    run_travel_planner,
    stream_travel_planner,
    TravelState,
)

__all__ = ["app", "run_travel_planner", "stream_travel_planner", "TravelState"]

if __name__ == "__main__":
    sample_query = "Plan a trip of 3 days to Goa on a mid budget"
    session_id = "user_trip_goa_root"
    print(f"Running backend planner for: '{sample_query}' with thread_id='{session_id}'...\n")
    result = run_travel_planner(sample_query, thread_id=session_id)
    print("\n" + "=" * 60)
    print("--- Final TravelState ---")
    print(f"Destination: {result.get('destination')}")
    print(f"Total LLM Calls: {result.get('llm_calls')}")
    print(f"\n🗺️ Master Itinerary Preview:\n{result.get('itinerary', '')[:800]}...")
    print("=" * 60 + "\n")