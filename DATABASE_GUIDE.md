# PostgreSQL Checkpointer & Session Memory Guide

This document details the PostgreSQL persistence architecture for the **TravelPlanner** application powered by **LangGraph**, **`PostgresSaver`**, and **`psycopg`**.

---

## 1. Architecture Overview

In a production travel planner, users start sessions, ask for flight options, browse itineraries, log out, and return later. To provide continuous, stateful interactions across server restarts and page refreshes, LangGraph uses **PostgreSQL Checkpointing**.

```
+-------------------------------------------------------------+
|                        User in UI                           |
|       (Logs in with User ID or Session ID: thread_id)       |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                    LangGraph TravelState                    |
|   - user_query      - flight_results     - hotel_results    |
|   - itinerary       - message (history)  - llm_calls        |
+------------------------------+------------------------------+
                               |
               Persisted after every node execution
                               |
                               v
+-------------------------------------------------------------+
|             PostgreSQL Database: travel_planner             |
|                                                             |
|  +-------------------+              +--------------------+  |
|  |    checkpoints    | <----------> |  checkpoint_blobs  |  |
|  +-------------------+              +--------------------+  |
|           |                                                 |
|           v                                                 |
|  +-------------------+              +--------------------+  |
|  | checkpoint_writes |              |checkpoint_migration|  |
|  +-------------------+              +--------------------+  |
+-------------------------------------------------------------+
```

---

## 2. The 4 Persistence Tables Explained

When `checkpointer.setup()` runs, four tables are created inside the `travel_planner` PostgreSQL schema.

### 1. `checkpoints`
- **Role:** The master state ledger.
- **Key Columns:**
  - `thread_id` (`text`): Unique identifier for a user or travel session (e.g. `user_101` or `satyam_trip_tokyo`).
  - `checkpoint_ns` (`text`): Checkpoint namespace (defaults to empty string `""` for the main graph).
  - `checkpoint_id` (`text`): UUID/Timestamp identifying the snapshot at that specific turn.
  - `parent_checkpoint_id` (`text`): Points to the prior state, forming an immutable history chain.
  - `type` (`text`): Serialization format identifier (e.g. `msgpack`, `json`).
  - `checkpoint` (`jsonb` / byte format): Metadata and high-level state snapshot.
  - `metadata` (`jsonb`): Information about the step that produced this checkpoint (source node, write step, etc.).

### 2. `checkpoint_blobs`
- **Role:** High-efficiency binary data storage.
- **Why it exists:** Complex state items—such as message objects, flight search text, large itinerary markdowns, and Python dictionaries—are serialized and stored here.
- **Benefit:** Prevents large payloads from slowing down index lookups in the main `checkpoints` table.

### 3. `checkpoint_writes`
- **Role:** Pending transaction and node-step journal.
- **Why it exists:** When a graph executes multi-node flows (`flight_agent` $\to$ `hotel_agent` $\to$ `itinerary_agent`), each node produces writes. If an external API fails midway, `checkpoint_writes` ensures:
  1. Atomic rollback and retry capabilities.
  2. Support for Human-in-the-Loop approvals (e.g. asking the user to confirm a budget before continuing).

### 4. `checkpoint_migrations`
- **Role:** Database version management.
- **Why it exists:** Tracks the schema version of the LangGraph Postgres checkpointer. As libraries upgrade, LangGraph uses this table to migrate schemas without corrupting existing user conversations.

---

## 3. Where User Agent Results are Stored

When `flight_agent_node` runs for a query like *"Plan a 7 day trip from Delhi to Tokyo"*, LangGraph does the following:

1. **Extracts IATA:** Maps Delhi $\to$ `DEL` and Tokyo $\to$ `HND`.
2. **Fetches Flights:** Retrieves 5 flights from AviationStack.
3. **Packages Output:**
   - `flight_results`: Formatted text of the 5 flights.
   - `message`: `[AIMessage("Found flight options for route DEL -> HND...")]`.
   - `llm_calls`: Incremented by 1.
4. **Commits to Postgres:** Stored in **`checkpoints`** and **`checkpoint_blobs`** under the provided **`thread_id`**.

---

## 4. How to Retrieve Stored Results When a User Logs In

When a user logs into your UI, you **do not write raw SQL**. Instead, use LangGraph's native `app.get_state()` method.

```python
from main import app

# 1. Provide the user's thread_id
config = {"configurable": {"thread_id": "user_session_101"}}

# 2. Fetch their latest saved state from PostgreSQL
state_snapshot = app.get_state(config)

if state_snapshot.values:
    saved_state = state_snapshot.values
    
    # Retrieve user's previous findings:
    user_query     = saved_state.get("user_query")
    flight_data    = saved_state.get("flight_results")
    messages       = saved_state.get("message")
    
    print(f"Welcome back! Last search: {user_query}")
    print(f"Previous flight options:\n{flight_data}")
else:
    print("New user session - no existing travel plan found.")
```

### Continuing Multi-Turn Conversations
If the user returns after a week and writes:
> *"Now find 4-star hotels in Tokyo for the same dates"*

Simply call `app.invoke()` with the **same `thread_id`**:

```python
from langchain_core.messages import HumanMessage

followup_query = "Now find 4-star hotels in Tokyo for the same dates"

result = app.invoke(
    {
        "message": [HumanMessage(content=followup_query)],
        "user_query": followup_query
    },
    config={"configurable": {"thread_id": "user_session_101"}}
)
```
LangGraph restores the previous state from PostgreSQL, gives your next agent the previous flight details (`DEL -> HND`), processes the hotel search, and saves a new checkpoint.

---

## 5. Recommended Session ID / `thread_id` Design

To separate users and trips cleanly in the database:

| Use Case | Suggested `thread_id` Format | Example |
| :--- | :--- | :--- |
| **Single chat per user** | `f"user_{user_id}"` | `user_42` |
| **Multiple trips per user** | `f"user_{user_id}_trip_{trip_id}"` | `user_42_trip_japan_2026` |
| **Anonymous guest** | `f"guest_{uuid4()}"` | `guest_d4f8e219` |

---

## 6. Useful SQL Queries for pgAdmin 4

Open the **Query Tool** on `travel_planner` in pgAdmin 4:

### 1. View all active user sessions
```sql
SELECT DISTINCT thread_id, count(*) AS total_steps 
FROM checkpoints 
GROUP BY thread_id;
```

### 2. View checkpoints for a specific user
```sql
SELECT thread_id, checkpoint_id, parent_checkpoint_id, metadata
FROM checkpoints 
WHERE thread_id = 'user_session_101'
ORDER BY checkpoint_id DESC;
```

### 3. Clear data for a single user (Reset conversation)
```sql
DELETE FROM checkpoints WHERE thread_id = 'user_session_101';
DELETE FROM checkpoint_writes WHERE thread_id = 'user_session_101';
DELETE FROM checkpoint_blobs WHERE thread_id = 'user_session_101';
```
