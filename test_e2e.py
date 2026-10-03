import sys
import os
import time
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.main import stream_travel_planner


def main():
    test_query = "Plan a trip of 3 days to Goa on a mid budget"
    session_id = f"test_e2e_{int(time.time())}"
    
    print("=" * 70)
    print(f"🚀 Starting End-to-End Travel Planner Test")
    print(f"Query: '{test_query}'")
    print(f"Session ID: {session_id}")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    start_total = time.time()
    
    for event in stream_travel_planner(test_query, thread_id=session_id):
        for node_name, node_state in event.items():
            node_time = time.time() - start_total
            print(f"\n[{node_time:.1f}s] ✅ COMPLETED NODE: {node_name.upper()}")
            
            if node_name == "weather_agent":
                print(f"  - Destination: {node_state.get('destination')}")
                print(f"  - Duration: {node_state.get('duration_days')} days")
                print(f"  - Recommended Date: {node_state.get('travel_date')}")
                print(f"  - Weather Summary Snippet:\n    {node_state.get('weather_results', '')[:250]}...")
            
            elif node_name == "flight_agent":
                print(f"  - Flight Results Snippet:\n    {node_state.get('flight_results', '')[:250]}...")
            
            elif node_name == "hotel_agent":
                print(f"  - Hotel Results Snippet:\n    {node_state.get('hotel_results', '')[:250]}...")
            
            elif node_name == "places_agent":
                images = node_state.get("place_images", [])
                print(f"  - Place Images Discovered: {len(images)}")
                for img in images[:3]:
                    print(f"    📸 {img.get('name')}: {img.get('url')[:60]}...")
                print(f"  - Places Results Snippet:\n    {node_state.get('places_results', '')[:250]}...")
            
            elif node_name == "itinerary_agent":
                print(f"  - Total LLM Calls: {node_state.get('llm_calls')}")
                itinerary_text = node_state.get('itinerary', '')
                print(f"  - Master Itinerary Length: {len(itinerary_text)} chars")
                print("\n" + "=" * 70)
                print("📋 FINAL MASTER ITINERARY PREVIEW:")
                print("=" * 70)
                print(itinerary_text[:1500])
                print("\n... [truncated preview] ...\n")
                
                # Verify key elements
                print("🔍 VERIFICATION CHECKS:")
                print(f"  1. Contains 'Goa': {'Goa' in itinerary_text or 'goa' in itinerary_text.lower()}")
                print(f"  2. Day-by-Day (Day 1, Day 2, Day 3): {'Day 1' in itinerary_text and 'Day 2' in itinerary_text and 'Day 3' in itinerary_text}")
                print(f"  3. Embedded Images (![...](...)): {'![' in itinerary_text}")
                print(f"  4. Financial Ledger / Budget Table: {'|' in itinerary_text and 'INR' in itinerary_text}")
                print(f"  5. Does NOT confuse with Genoa: {'Genoa' not in itinerary_text and 'Italy' not in itinerary_text}")
                print("=" * 70)
    
    total_elapsed = time.time() - start_total
    print(f"\n🎉 Test completed successfully in {total_elapsed:.1f} seconds ({total_elapsed/60:.2f} minutes)!")

if __name__ == "__main__":
    main()
