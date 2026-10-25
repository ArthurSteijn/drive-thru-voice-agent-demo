# Plan: DriveThru Voice Agent MVP

**TL;DR**: Build a minimal working demo where a React frontend captures microphone audio, streams it over WebSocket to a thin Python relay backend (FastAPI), which proxies the session to Azure VoiceLive using **Approach 2: Foundry Agent Integration**. The relay authenticates via `DefaultAzureCredential`, connects to the VoiceLive WebSocket with `agent-project-name` + `agent-id` + `agent-access-token` query params, and streams audio bidirectionally. The Azure AI Foundry Agent (created via `platform/aif-resources/create-foundry-agent.ipynb`) owns all instructions, personality, and tool execution — no client-side function calling needed.

---

## Azure Resources — What needs to be deployed and how

| Resource | Status | How to provision |
|---|---|---|
| Azure Resource Group `rg-voiceliveapi-demo` | ✅ Scripted | `platform/aif-resources/resource-setup.azcli` |
| Azure AI Services `aif-voiceliveapi-demo` (Foundry Hub) | ✅ Scripted | `platform/aif-resources/resource-setup.azcli` |
| Azure AI Foundry Project `prj-voiceliveapi-demo` | ✅ Scripted | `platform/aif-resources/resource-setup.azcli` |
| **`gpt-realtime` model deployment** | ✅ Scripted | `platform/aif-resources/resource-setup.azcli` (added `az cognitiveservices account deployment create`) |
| **Microsoft Fabric Database** | ✅ Done | Schema applied via `src/fabric/schema-setup.sql`; connection string added to `.env` |
| **Azure Foundry Agent (Order Agent)** | ❌ Notebook | Run `platform/aif-resources/create-foundry-agent.ipynb` after `.env` is populated |

> No additional Azure infra (App Service, Container App, etc.) is needed for the MVP — the relay backend runs locally via `uv run`.

---

## Steps

### 1. Populate `.env`

Create `.env` at the repo root (see `.env.example` for template):

```
PROJECT_ENDPOINT="https://aif-voiceliveapi-demo.services.ai.azure.com/api/projects/proj-voiceliveapi-demo"
AGENT_NAME="drivethru-ordering-agent"
MODEL_DEPLOYMENT_NAME="gpt-5.4"
VOICELIVE_ENDPOINT="https://aif-voiceliveapi-demo.services.ai.azure.com/"
VOICELIVE_API_VERSION="2026-04-10"
PROJECT_NAME="proj-voiceliveapi-demo"
FABRIC_CONNECTION_STRING=Driver={ODBC Driver 18 for SQL Server};Server=...;Database=DriveThru;...
```

Auth uses `DefaultAzureCredential` — no API key needed (`az login` or Managed Identity).
Requires **Azure AI User** + **Cognitive Services User** RBAC roles on the Foundry resource.

---

### 2. Deploy `gpt-realtime` model (✅ now scripted)

Added to `platform/aif-resources/resource-setup.azcli`:
```
az cognitiveservices account deployment create \
    --name aif-voiceliveapi-demo \
    --resource-group rg-voiceliveapi-demo \
    --deployment-name gpt-realtime \
    --model-name gpt-4o-realtime-preview \
    --model-version 2025-04-01 \
    --model-format OpenAI \
    --sku-capacity 1 \
    --sku-name GlobalStandard
```

Alternatively, deploy manually in the AI Foundry portal (`ai.azure.com`):
1. Open project `prj-voiceliveapi-demo` → **Deployments** → **Deploy model**
2. Select `gpt-4o-realtime-preview`, name it `gpt-realtime`
3. Region must be `swedencentral`

---

### 3. Provision Fabric Database (✅ Done)

1. Fabric SQL Database `DriveThru` created with workspace
2. Schema applied via `src/fabric/schema-setup.sql` (creates all tables, indexes, `OrderAnalytics` view, seeds 8 menu items)
3. ODBC connection string added to `.env` as `FABRIC_CONNECTION_STRING`

---

### 4. Create the Azure Foundry Agent (❌ notebook)

Run `platform/aif-resources/create-foundry-agent.ipynb` — cell 5 calls `create_version` with the DriveThru ordering instructions. Copy the printed agent ID into `.env` as `AZURE_VOICELIVE_AGENT_ID`.

The Agent owns all instructions and tool schemas. The relay (`src/backend/relay.py`) only streams audio.

---

### 5. ~~Implement `src/fabric/db_client.py`~~ ✅ Done

Implemented `FabricDBClient` with `get_menu()` and `submit_order()` methods using `pyodbc` parameterised queries.

---

### 6. ~~Implement agent tool wrappers~~ ✅ Done

Implemented `src/agent_tools/menu_tools.py` and `src/agent_tools/order_tools.py` with JSON schemas and executor functions.

---

### 7. ~~Build the FastAPI relay backend~~ ✅ Refactored & Streamlined

Implemented `src/backend/relay.py` — **Approach 2** relay using raw `websockets`. Decomposed and streamlined down to < 80 lines using single-responsibility modules:
- [`src/backend/config.py`](../src/backend/config.py)
- [`src/backend/tool_dispatcher.py`](../src/backend/tool_dispatcher.py)
- [`src/backend/event_handlers.py`](../src/backend/event_handlers.py)

See [Wiki Architecture Specs](./architecture-specs.md).

---

### 8. ~~Build the React frontend~~ ✅ Done

Implemented `src/frontend/` — Vite + React + TypeScript with mic capture via AudioWorklet, PCM16 streaming, audio playback, status indicator, transcript display, and order summary panel.

---

### 9. ~~Wire relay to serve frontend~~ ✅ Done

VS Code `.vscode/tasks.json` created with `dev: full stack` compound task. Vite dev server proxies `/ws/voice` to the backend. Production build served by FastAPI `StaticFiles` mount.

---

## Verification

```powershell
# 1. Start relay backend
uv run uvicorn src.backend.relay:app --reload --port 8000

# 2. (Dev mode) Start Vite dev server with proxy to backend
cd src/frontend ; npm run dev
```

- Open `http://localhost:5173`, press mic, order a burger
- Agent responds via voice
- Check Fabric DB: `SELECT * FROM Orders ORDER BY CreatedAt DESC`
- Azure AI Foundry portal → **Tracing** shows the agent session with tool calls

---

## Key Decisions

| Decision | Rationale |
|---|---|
| Approach 2 (Foundry Agent) over Approach 1 (direct model + client tools) | Agent autonomously handles tools — simpler relay, no function calling code on server |
| Relay backend (FastAPI) over direct browser WebSocket | Keeps credentials server-side; relay proxies audio only |
| Raw `websockets` over `azure-ai-voicelive` SDK | Reference pattern uses raw WS with `agent-project-name` + `agent-id` query params; SDK v1.1.0 doesn't yet support `agent_config` param |
| Foundry Agent created via notebook | One-time setup step — `platform/aif-resources/create-foundry-agent.ipynb`; provides versioning and portal tracing |
| `DefaultAzureCredential` over API key | No secrets stored in `.env`; uses `az login` or Managed Identity |
| `uv` for all Python deps | Already established in the project; faster than pip, lockfile-friendly |
