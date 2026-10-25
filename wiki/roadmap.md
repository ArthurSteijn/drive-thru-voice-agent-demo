# DriveThru MVP — Remaining Steps

> Last updated: 2026-04-07

## Done

- [x] Azure resources provisioned (`platform/aif-resources/resource-setup.azcli`)
- [x] `src/fabric/db_client.py` — FabricDBClient (get_menu, submit_order)
- [x] `src/agent_tools/` — menu_tools.py + order_tools.py schemas & executors
- [x] `src/backend/relay.py` — WebSocket relay (browser ↔ VoiceLive ↔ Foundry Agent)
- [x] `src/frontend/` — React + TypeScript, AudioWorklet PCM16 mic capture, audio playback
- [x] `.vscode/tasks.json` — `dev: full stack` compound task
- [x] `platform/aif-resources/create-foundry-agent.ipynb` — agent creation notebook
- [x] **SDK update** — `azure-ai-projects` 2.0.1 (stable), RBAC roles in setup script
- [x] **Auth fixes** — relay uses `agent-name` (not `agent-id`), canonical env vars, RBAC roles added to `resource-setup.azcli`
- [x] **Env consolidation** — single set of env vars in `.env.example`, no legacy duplicates
- [x] **Function calling wired up** — relay handles `response.function_call_arguments.done` and dispatches to executors over the WebSocket (no HTTP callbacks needed — VoiceLive uses the OpenAI Realtime function-calling protocol)
- [x] **Demo data seeder** — `python -m src.fabric.seed_demo_data` populates Menu/Customers/Orders with realistic synthetic data (~25 menu items, 12 customers, ~1500 orders with lunch/dinner peaks); idempotent via MERGE; covered by 28 unit tests

## To Do

- [ ] **Fabric DB** — go to [app.fabric.microsoft.com](https://app.fabric.microsoft.com), create SQL database `DriveThru`, run `src/fabric/schema-setup.sql`, add `FABRIC_CONNECTION_STRING` to `.env`
- [ ] **Start the full stack** — `uvicorn src.backend.relay:app --reload` + `cd src/frontend && npm run dev`
- [ ] **End-to-end test** — open `http://localhost:5173`, press mic, order a burger

## Related

- [planning.md](./planning.md) — full MVP plan with architecture decisions
- [agent-workflow.md](./agent-workflow.md) — development patterns
