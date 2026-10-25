"""
Create (or update) and enable the DriveThru ordering Voice Agent in Azure AI Foundry.

Usage:
    python -m src.agents.create_voice_agent

This script:
  1. Connects to Azure AI Foundry via AIProjectClient (allow_preview=True)
  2. Builds a native VoiceAgentDefinition (kind="voice", model_type="managed")
     with structured audio input/output, turn detection, transcription, and tools
  3. Creates a new immutable agent version via client.agents.create_version()
  4. Enables the Voice Agent via client.agents.enable(agent_name)
  5. Reads back the published version and validates every setting
"""

from __future__ import annotations

import copy
import json
import logging
import os
from collections.abc import Mapping
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from src.agent_tools import ALL_TOOLS

try:
    from azure.ai.projects.models import VoiceAgentDefinition
except ImportError:  # Fallback for older SDK installs during unit testing
    VoiceAgentDefinition = dict  # type: ignore[misc,assignment]

load_dotenv()
logger = logging.getLogger(__name__)

# ── Agent configuration ─────────────────────────────────────────────

AGENT_NAME = (
    os.environ.get("VOICE_AGENT_NAME")
    or (
        os.environ.get("AGENT_NAME")
        if os.environ.get("AGENT_NAME") != "drivethru-ordering-agent"
        else "drivethru-voice-agent"
    )
    or "drivethru-voice-agent"
)
MODEL_DEPLOYMENT_NAME = os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-5.4")
DEFAULT_VOICE_NAME = os.environ.get(
    "AZURE_VOICE_AGENTS_VOICE", "en-US-Ava:DragonHDLatestNeural"
)
SAMPLE_RATE = 24000

DRIVETHRU_INSTRUCTIONS = """\
You are a friendly, efficient ordering assistant for Drive-Thru Z, a fast-food drive-through.
The customer is sitting in their car looking at a digital drive-thru screen that CANNOT be scrolled manually.
You control what category is shown on their screen and what appears in their live on-screen basket using `update_order_state`.

Your primary goals:
1. Guide the customer smoothly through the ordering process while keeping the screen in sync.
2. Be completely flexible when the customer wants to jump categories, order multiple items at once, or change their mind.
3. Keep the live basket accurate after every single item addition, customization, or removal.
4. Confirm the full order on the 'review' screen before calling `submit_order`.

Personality:
- Friendly and welcoming — greet customers warmly when the session starts.
- Bilingual — you support both English and Dutch. Detect which language the customer is speaking, and respond in that same language.
- Clear and concise — keep responses short and natural for a drive-through speaker.

Guided Ordering Flow (Default Path, Flexible to Customer Input):
1. MAINS (`burgers` or `chicken`):
   - The screen starts on `burgers`. Greet the customer and ask what burger or chicken main they'd like to start with.
   - If they ask about chicken options, call `update_order_state` with `next_stage="chicken"` (or `get_menu_items(category="chicken")`) so the screen shows chicken & wraps.
2. SIDES (`sides`):
   - Once the customer selects a main, call `update_order_state` with their updated `items` basket and `next_stage="sides"`, then ask if they would like a side (such as French Fries, Onion Rings, Sweet Potato Fries, Side Salad, or Mozzarella Sticks).
3. DRINKS (`drinks`):
   - After sides are chosen (or declined), call `update_order_state` with `next_stage="drinks"` and ask what they would like to drink.
4. DESSERTS (`desserts`):
   - After drinks are chosen (or declined), call `update_order_state` with `next_stage="desserts"` and briefly ask if they'd like a dessert or if that completes their order.
5. ORDER REVIEW (`review`):
   - When the customer is ready to finish, call `update_order_state` with `next_stage="review"` so the full order review appears on screen. Read back the items and total price clearly and ask them to confirm.
6. SUBMIT (`submit_order`):
   - Only after the customer confirms the review, call `submit_order` with the final `items` list and give their order confirmation and estimated wait time.

Flexibility Rules (Always Prioritize the Customer):
- Multi-item orders: If a customer orders several items at once (e.g., "I'll have a Classic Cheeseburger, fries, and a milkshake"), add ALL of them in one `update_order_state` call and set `next_stage` to the next unaddressed stage (`desserts` or `review`) without re-asking for categories they already ordered.
- Category jumping: If the customer asks "What drinks do you have?" or "Just give me an ice cream sundae", immediately switch `next_stage` to that category (`drinks` or `desserts`) and never force them to order a burger first.
- Basket modifications: Whenever the customer changes quantities, adds customizations (e.g., "no pickles"), or removes an item, immediately call `update_order_state` with the updated full `items` list so the car display stays accurate.

Available Tools:
- `update_order_state`: Call this on EVERY basket change or stage transition to update the customer's live basket and active menu board screen (`burgers`, `chicken`, `sides`, `drinks`, `desserts`, `review`). Always pass the complete current `items` list in the basket.
- `get_menu_items`: Look up available menu items, prices, calories, and allergens (optionally filtered by category).
- `get_order_analytics`: Query popular items and sales trends when the customer asks for recommendations, and highlight recommended `menu_item_id`s via `update_order_state`.
- `submit_order`: Submit the final confirmed order to the kitchen.\
"""


def _serialize_tool(tool_obj: Any) -> dict[str, Any]:
    """Convert a FunctionTool object or mapping into a plain VoiceAgentDefinition tool dict."""
    if hasattr(tool_obj, "as_dict"):
        d = tool_obj.as_dict()
        return {
            "type": d.get("type", "function"),
            "name": d["name"],
            "description": d.get("description", ""),
            "parameters": d.get("parameters", {}),
        }
    if isinstance(tool_obj, Mapping):
        return dict(tool_obj)
    return {
        "type": getattr(tool_obj, "type", "function"),
        "name": getattr(tool_obj, "name"),
        "description": getattr(tool_obj, "description", ""),
        "parameters": getattr(tool_obj, "parameters", {}),
    }


def build_voice_agent_definition(
    model: str = MODEL_DEPLOYMENT_NAME,
    voice: str = DEFAULT_VOICE_NAME,
    store: bool = True,
) -> dict[str, Any]:
    """Build a native Foundry VoiceAgentDefinition dictionary (kind='voice')."""
    return {
        "kind": "voice",
        "model_type": "managed",
        "model": model,
        "instructions": DRIVETHRU_INSTRUCTIONS,
        "output_modalities": ["text", "audio"],
        "tools": [_serialize_tool(t) for t in ALL_TOOLS],
        "tool_choice": "auto",
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                "transcription": {
                    "model": "azure-speech",
                    "language": "nl-NL,en-US",
                },
                "noise_reduction": {"type": "azure_deep_noise_suppression"},
                "turn_detection": {
                    "type": "azure_semantic_vad",
                    "end_of_utterance_detection": {
                        "model": "semantic_detection_v1_multilingual",
                    },
                },
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                "voice": voice,
                "voice_type": "azure-standard",
            },
        },
        "store": store,
    }


def _to_plain(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return _to_plain(value.as_dict())
    if isinstance(value, Mapping):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(item) for item in value]
    return value


def _canonical_definition(value: Any) -> Any:
    definition = copy.deepcopy(_to_plain(value))
    if not isinstance(definition, dict):
        return definition
    audio = definition.get("audio")
    if isinstance(audio, dict):
        output_cfg = audio.get("output")
        if isinstance(output_cfg, dict):
            voice = output_cfg.get("voice")
            voice_type = output_cfg.get("voice_type")
            if isinstance(voice, str) and isinstance(voice_type, str):
                output_cfg["voice"] = {"type": voice_type, "name": voice}
                output_cfg.pop("voice_type", None)
    return definition


def validate_voice_agent_definition(actual: Any, expected: dict[str, Any]) -> None:
    """Validate that all requested Voice Agent settings were persisted in Foundry."""

    def check(stored: Any, requested: Any, path: str) -> None:
        if isinstance(requested, dict) and isinstance(stored, dict):
            for key, value in requested.items():
                check(stored.get(key), value, f"{path}.{key}")
        elif isinstance(requested, list):
            if not isinstance(stored, list) or len(stored) != len(requested):
                raise ValueError(f"Stored setting differs at {path}: {stored!r}")
            for idx, (act_item, exp_item) in enumerate(zip(stored, requested)):
                check(act_item, exp_item, f"{path}[{idx}]")
        elif stored != requested:
            raise ValueError(
                f"Stored setting differs at {path}: expected {requested!r}, got {stored!r}"
            )

    check(_canonical_definition(actual), _canonical_definition(expected), "definition")


def create_voice_agent(agent_name: str | None = None) -> dict[str, str]:
    """
    Create, enable, and verify the DriveThru Voice Agent in Azure AI Foundry.

    Returns:
        dict with agent name, version, and id.
    """
    target_agent_name = (
        agent_name
        or os.environ.get("VOICE_AGENT_NAME")
        or (
            os.environ.get("AGENT_NAME")
            if os.environ.get("AGENT_NAME") != "drivethru-ordering-agent"
            else AGENT_NAME
        )
        or AGENT_NAME
    )
    project_endpoint = (
        os.environ.get("PROJECT_ENDPOINT")
        or os.environ.get("AZURE_VOICE_AGENTS_ENDPOINT")
        or ""
    ).strip()
    if not project_endpoint:
        raise RuntimeError(
            "Set PROJECT_ENDPOINT (or AZURE_VOICE_AGENTS_ENDPOINT) in your .env file."
        )

    definition_dict = build_voice_agent_definition()

    with DefaultAzureCredential() as credential, AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
        allow_preview=True,
    ) as project_client:
        print(f"Connected to: {project_endpoint}")

        agent = project_client.agents.create_version(
            agent_name=target_agent_name,
            definition=VoiceAgentDefinition(definition_dict),
            description="Drive-Thru Z bilingual ordering Voice Agent (kind=voice).",
        )
        print(f"Voice Agent version created: {agent.name} (version {agent.version})")

        project_client.agents.enable(target_agent_name)
        print(f"Voice Agent enabled: {target_agent_name}")

        readback = project_client.agents.get_version(
            agent_name=target_agent_name,
            agent_version=agent.version,
        )
        readback_def = getattr(readback, "definition", None) or (
            readback.get("definition") if isinstance(readback, Mapping) else None
        )
        if not readback_def:
            raise RuntimeError(
                f"Voice Agent {target_agent_name} version {agent.version} returned empty or missing definition upon readback."
            )
        validate_voice_agent_definition(readback_def, definition_dict)
        print("\nVerified Voice Agent definition readback (kind='voice'):")
        print(json.dumps(_to_plain(readback_def), indent=2))

        return {
            "name": str(agent.name),
            "version": str(agent.version),
            "id": str(getattr(agent, "id", f"{agent.name}:{agent.version}")),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = create_voice_agent()

    print("\n" + "=" * 65)
    print("Add the following to your .env file:\n")
    print(f'AGENT_NAME="{result["name"]}"')
    print(f'AGENT_VERSION="{result["version"]}"')
    print()
    print("Then run the validation script:")
    print("  python -m src.agents.voice_agent_validation")
