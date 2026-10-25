# Architecture Specifications & Backend Decomposition

This document details the modular architecture, component responsibilities, and design decisions for the VoiceLive API DriveThru Agent Demo backend.

---

## 🏗️ Backend Relay Architecture

### Objective
The backend relay provides a high-performance, asynchronous bridge between the web browser and the Azure VoiceLive API. The backend was decomposed from a monolithic file into four cohesive, independently testable modules in `src/backend/`.

```
src/backend/
├── config.py           # Environment, Azure AD token handling & session defaults
├── tool_dispatcher.py  # Function call execution router & JSON formatting
├── event_handlers.py   # RelaySessionState dataclass & VoiceLive event handlers
├── diagnostics.py      # Health checks & latency diagnostics
└── relay.py            # Streamlined FastAPI WebSocket entrypoint (< 80 lines)
```

---

## 🧩 Module Responsibilities

### 1. `src/backend/config.py`
- Manages canonical environment variables (`VOICELIVE_ENDPOINT`, `AGENT_NAME`, `PROJECT_NAME`, `VOICELIVE_API_VERSION`).
- Implements cached Azure AD token retrieval via `DefaultAzureCredential` (`get_azure_token()`).
- Assembles the VoiceLive WebSocket URL with URL-encoded query parameters (`build_ws_url()`).

### 2. `src/backend/tool_dispatcher.py`
- Dispatches agent function calls (`get_menu_items`, `submit_order`, `get_order_analytics`).
- Encapsulates tool output formatting and sends `conversation.item.create` events back to VoiceLive.
- Handles parameter validation and error formatting.

### 3. `src/backend/event_handlers.py`
- **`RelaySessionState`**: Tracks session state per connection (in-flight function calls, speech start/stop, response cancellations).
- **`process_voicelive_event()`**: Modular handler map replacing monolithic `if/elif` loops, processing audio buffers, user transcriptions, agent voice streams, and function call completions.

### 4. `src/backend/relay.py`
- Pure WebSocket relay server connecting browser clients to VoiceLive API.
- Mounts HTTP routes: `/health`, `/api/menu`, and static assets.
- Manages dual WebSocket message pumping (`client -> voicelive` and `voicelive -> client`).

---

## 🧪 Testing & Verification Strategy

All backend modules are verified using unit tests:

```powershell
uv run pytest tests/test_backend_config.py tests/test_event_handlers.py tests/test_tool_dispatcher.py -v
```

Tests cover:
- WebSocket URL construction and query parameter formatting
- Token acquisition and caching
- Tool execution routing and error response envelopes
- Event processing for speech starts, audio streaming, and session cancellation
