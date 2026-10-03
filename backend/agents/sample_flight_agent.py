import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from langchain_core.messages import AIMessage
try:
    from backend.tools.flight_tool import flight_search
except ImportError:
    from tools.flight_tool import flight_search

load_dotenv()

# Initialize OpenAI client pointing to Hugging Face's OpenAI-compatible router
llm_client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.getenv("HF_TOKEN")
)

ROUTE_EXTRACTION_PROMPT = """You are a travel route specialist.
Analyze the user's travel request and extract the departure and destination airport IATA codes (3-letter uppercase codes).

Rules:
1. Map city or country names to their primary international airport IATA code:
   - Delhi -> DEL
   - Mumbai -> BOM
   - Tokyo / Japan -> HND
   - London / UK -> LHR
   - Paris / France -> CDG
   - New York -> JFK
2. If the user does NOT mention a departure place, default departure_iata to "DEL".

CRITICAL: Return ONLY a raw valid JSON block matching this exact schema:
{
  "departure_iata": "AAA",
  "arrival_iata": "BBB"
}
"""

def flight_agent_node(state: dict) -> dict:
    user_query = state.get("user_query", "")
    try:
        response = llm_client.chat.completions.create(
            model="meta-llama/Llama-3.3-70B-Instruct",
            messages=[
                {"role": "system", "content": ROUTE_EXTRACTION_PROMPT},
                {"role": "user", "content": user_query}
            ],
            temperature=0.0
        )
        raw_content = response.choices[0].message.content.strip()
        if raw_content.startswith("```"):
            raw_content = raw_content.replace("```json", "").replace("```", "").strip()
        parsed_json = json.loads(raw_content)
        dep_iata = parsed_json.get("departure_iata", "DEL").strip().upper()
        arr_iata = parsed_json.get("arrival_iata", "").strip().upper()
    except Exception as e:
        err_msg = f"Unable to identify flight route from query: {str(e)}"
        return {
            "flight_results": err_msg,
            "message": [AIMessage(content=err_msg)],
            "llm_calls": state.get("llm_calls", 0) + 1
        }

    try:
        flights_data = flight_search(departure_iata=dep_iata, arrival_iata=arr_iata)
        flight_results = f"Route: {dep_iata} -> {arr_iata}\n\n{flights_data}"
    except Exception as e:
        flight_results = f"Error fetching flights between {dep_iata} and {arr_iata}: {str(e)}"

    return {
        "flight_results": flight_results,
        "message": [AIMessage(content=f"Found flight options for route {dep_iata} -> {arr_iata}:\n\n{flight_results}")],
        "llm_calls": state.get("llm_calls", 0) + 1
    }
