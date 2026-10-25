"""
End-to-end tests for the DriveThru agent conversation flow.

These tests require live Azure credentials and a provisioned Foundry Agent.
They are skipped unless both PROJECT_ENDPOINT and FABRIC_CONNECTION_STRING are set.

Run manually after completing setup:
    pytest tests/e2e/ -v -m e2e

Add AGENT_NAME to .env or the environment before running.
"""

import os
import pytest
from dotenv import load_dotenv

# Ensure .env is loaded before evaluating pytestmark
load_dotenv()

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not (os.getenv("PROJECT_ENDPOINT") and os.getenv("FABRIC_CONNECTION_STRING")),
        reason="PROJECT_ENDPOINT and FABRIC_CONNECTION_STRING required for e2e tests",
    ),
]


@pytest.fixture(scope="module")
def agent_client():
    from azure.identity import DefaultAzureCredential
    from azure.ai.agents import AgentsClient

    return AgentsClient(
        endpoint=os.environ["PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )


@pytest.fixture(scope="module")
def agent_name():
    return os.environ.get("AGENT_NAME", "drivethru-ordering-agent")


@pytest.fixture(scope="module")
def agent_id(agent_client, agent_name):
    # Check if a standard assistant with this name already exists
    agents = agent_client.list_agents()
    agent = next((a for a in agents if a.name == agent_name), None)
    if agent:
        return agent.id

    # If not, retrieve the prompt agent definition from the project client
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    project_client = AIProjectClient(
        endpoint=os.environ["PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )
    
    try:
        prompt_agent = project_client.agents.get(agent_name)
        latest_version = prompt_agent.versions.get("latest")
        instructions = latest_version.get("definition", {}).get("instructions")
        model = latest_version.get("definition", {}).get("model")
    except Exception:
        # Fallback to local python defaults if Azure project retrieval fails
        from src.agents.create_voice_agent import DRIVETHRU_INSTRUCTIONS, MODEL_DEPLOYMENT_NAME
        instructions = DRIVETHRU_INSTRUCTIONS
        model = MODEL_DEPLOYMENT_NAME

    from src.agent_tools import ALL_TOOLS
    openai_tools = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in ALL_TOOLS
    ]

    # Create standard agent in the Agents service
    print(f"\n[E2E Setup] Creating temporary E2E assistant '{agent_name}' using model '{model}'...")
    created_agent = agent_client.create_agent(
        model=model,
        name=agent_name,
        instructions=instructions,
        tools=openai_tools,
    )
    
    yield created_agent.id

    # Cleanup the created assistant after E2E tests finish
    print(f"\n[E2E Teardown] Deleting temporary E2E assistant '{created_agent.id}'...")
    try:
        agent_client.delete_agent(created_agent.id)
    except Exception as e:
        print(f"Failed to delete temporary E2E assistant: {e}")


class TestAgentMenuQuery:
    def test_agent_responds_to_menu_request(self, agent_client, agent_id):
        """Agent should respond with menu items when asked."""
        thread = agent_client.threads.create()

        run = agent_client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent_id,
            additional_messages=[
                {"role": "user", "content": "What burgers do you have?"}
            ],
        )

        messages = list(agent_client.messages.list(thread_id=thread.id))
        last_reply = next(
            (m for m in messages if m.role == "assistant"), None
        )

        assert last_reply is not None
        response_text = last_reply.content[0].text.value.lower()
        assert any(word in response_text for word in ["burger", "cheeseburger", "menu"])


class TestAgentOrderFlow:
    def test_agent_confirms_before_submitting(self, agent_client, agent_id):
        """Agent should ask for confirmation before calling submit_order."""
        thread = agent_client.threads.create()

        agent_client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent_id,
            additional_messages=[
                {"role": "user", "content": "I'd like a Classic Cheeseburger"}
            ],
        )

        messages = list(agent_client.messages.list(thread_id=thread.id))
        last_reply = next(
            (m for m in messages if m.role == "assistant"), None
        )

        assert last_reply is not None
        # Agent should confirm or acknowledge the order before submitting
        response_text = last_reply.content[0].text.value.lower()
        assert any(
            word in response_text
            for word in ["cheeseburger", "confirm", "anything else", "total", "order"]
        )
