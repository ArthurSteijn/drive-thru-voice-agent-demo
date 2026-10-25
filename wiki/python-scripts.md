# Python Scripts for Agent Development

This project uses modular **Python scripts and packages** for agent development, testing, database seeding, and runtime relays.

---

## 🎯 Script & Package Architecture

```
src/
├── __init__.py
├── agents/
│   ├── __init__.py
│   ├── create_voice_agent.py        # Provisions & registers Foundry agent + tool schemas
│   ├── voice_agent_validation.py    # Local mic & speaker validation via VoiceLive SDK
│   └── analytics_agent.py           # Analytics agent queries & insights
├── agent_tools/
│   ├── __init__.py                  # Exports get_menu_tool, submit_order_tool, analytics_tool
│   ├── menu_tools.py                # Menu query schema & execute_get_menu_items
│   ├── order_tools.py               # Order submission schema & execute_submit_order
│   └── analytics_tools.py           # Analytics query schema & execute_get_order_analytics
├── backend/
│   ├── __init__.py
│   ├── config.py                    # Canonical env vars & DefaultAzureCredential caching
│   ├── tool_dispatcher.py           # In-process function call dispatching & formatting
│   ├── event_handlers.py            # RelaySessionState & VoiceLive event handlers
│   ├── relay.py                     # Streamlined FastAPI WebSocket entrypoint
│   └── diagnostics.py               # Health & diagnostics endpoints
└── fabric/
    ├── __init__.py
    ├── db_client.py                 # FabricDBClient (ODBC connection & SQL queries)
    ├── schema-setup.sql             # SQL table definitions (Menu, Customers, Orders)
    ├── demo_data.py                 # Synthetic data generators (25 menu items, 12 customers)
    └── seed_demo_data.py            # Idempotent MERGE database seeder
```

---

## 🚀 Key Scripts & CLI Usage

### 1. Seed Demo Data in Fabric Database
Populates the Microsoft Fabric SQL Database with initial menu items, test customers, and synthetic order history:

```powershell
# Set FABRIC_CONNECTION_STRING in .env
python -m src.fabric.seed_demo_data
```

This script:
- Connects via `FabricDBClient`
- Executes idempotent SQL `MERGE` statements to avoid duplicates
- Seeds ~25 items across 5 categories, customer profiles, and sample orders

### 2. Create / Register the Voice Agent in Azure AI Foundry
Provisions or updates the DriveThru agent definition, attaches function tools, and stores VoiceLive settings in agent metadata:

```powershell
python -m src.agents.create_voice_agent
```

This script:
- Authenticates using `DefaultAzureCredential` via `AIProjectClient`
- Registers schemas for `get_menu_items`, `submit_order`, and `get_order_analytics`
- Sets the system prompt with drive-through ordering instructions
- Prints the assigned `AGENT_NAME` and `AGENT_VERSION`

### 3. Validate the Agent with Microphone & Audio
Interacts directly with the VoiceLive API from your terminal using your local microphone and speakers:

```powershell
python -m src.agents.voice_agent_validation
```

Features:
- Live streaming of audio input to VoiceLive
- Real-time speech response playback
- In-process execution of tool calls (`get_menu_items`, `submit_order`)
- Full session logging in `logs/`

### 4. Run the Backend Relay
Launches the FastAPI WebSocket relay server for the web frontend:

```powershell
uv run uvicorn src.backend.relay:app --reload --port 8000
```

Endpoints:
- `GET /health` — Relay health check and diagnostics
- `GET /api/menu` — Direct REST endpoint to retrieve menu items
- `WS /ws/voice` — Bi-directional WebSocket bridging browser audio to Azure VoiceLive

---

## 🛠️ Tool Definition Pattern

Each agent tool in `src/agent_tools/` defines:
1. A `FunctionTool` schema registered with the Foundry agent.
2. An asynchronous/synchronous execution function that runs inside the relay when invoked by the agent.

### Example: Menu Tool (`src/agent_tools/menu_tools.py`)

```python
from azure.ai.projects.models import FunctionTool

# 1. Define schema for Foundry Agent
get_menu_tool = FunctionTool(
    name="get_menu_items",
    description="Retrieves available menu items with prices, descriptions, and calories.",
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["burgers", "chicken", "sides", "drinks", "desserts"],
                "description": "Category to filter by",
            },
            "search_term": {
                "type": "string",
                "description": "Optional keyword search",
            },
        },
    },
)

# 2. Execution function dispatched during function calls
def execute_get_menu_items(arguments: dict, db_client=None) -> dict:
    category = arguments.get("category")
    search_term = arguments.get("search_term")
    # Query database and return JSON-serializable dictionary
    ...
```

All tools are exported via `src/agent_tools/__init__.py` in the `ALL_TOOLS` list for clean registration in `create_voice_agent.py`.

---

## 🧪 Testing Python Scripts

Run the comprehensive pytest suite:

```powershell
# Run all unit tests
uv run pytest tests/unit -v

# Run backend relay unit tests
uv run pytest tests/test_backend_config.py tests/test_event_handlers.py tests/test_tool_dispatcher.py -v
```

---

## 💡 Best Practices

1. **Authentication**: Rely on `DefaultAzureCredential` for Azure services and avoid hardcoding secrets.
2. **Schema & Dispatch Alignment**: Whenever modifying a tool schema in `src/agent_tools/`, ensure the execution function is updated and re-run `create_voice_agent.py` to update the agent in Azure Foundry.
3. **Idempotence**: Database management scripts should use `MERGE` or conditional checks so they can be re-run safely in automated pipelines.
