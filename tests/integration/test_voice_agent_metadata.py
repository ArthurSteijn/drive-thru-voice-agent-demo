"""Integration tests for verifying the native Voice Agent definition in Azure AI Foundry."""

import os
import pytest
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), "../../.env")
load_dotenv(dotenv_path=dotenv_path)

from src.agents.create_voice_agent import (
    build_voice_agent_definition,
    validate_voice_agent_definition,
)


@pytest.mark.timeout(30)
def test_voice_agent_definition_has_kind_voice():
    """Verify that the latest version of the agent is a native Voice Agent (kind='voice')."""
    project_endpoint = os.environ.get("PROJECT_ENDPOINT") or os.environ.get(
        "AZURE_VOICE_AGENTS_ENDPOINT"
    )
    agent_name = (
        os.environ.get("VOICE_AGENT_NAME")
        or (
            os.environ.get("AGENT_NAME")
            if os.environ.get("AGENT_NAME") != "drivethru-ordering-agent"
            else "drivethru-voice-agent"
        )
        or "drivethru-voice-agent"
    )

    if not project_endpoint or not agent_name:
        pytest.skip(
            "PROJECT_ENDPOINT and AGENT_NAME environment variables must be set for integration tests"
        )

    with DefaultAzureCredential() as credential, AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
        allow_preview=True,
    ) as project_client:
        try:
            agent = project_client.agents.get(agent_name=agent_name)
        except Exception as exc:
            pytest.skip(f"Voice agent '{agent_name}' not yet deployed to Foundry: {exc}")

        assert agent, f"Failed to retrieve agent: {agent_name}"

        latest_version = agent.versions.get("latest")
        assert latest_version, "No versions found for the agent"

        definition = latest_version.get("definition", {})
        assert definition.get("kind") == "voice", (
            f"Expected agent definition kind='voice', got {definition.get('kind')!r}"
        )
        validate_voice_agent_definition(definition, build_voice_agent_definition())
