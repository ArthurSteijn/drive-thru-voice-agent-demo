"""Unit tests for VoiceAgentDefinition builder and readback validator."""

import pytest
from unittest.mock import MagicMock, patch

from src.agent_tools import ALL_TOOLS
from src.agents.create_voice_agent import (
    AGENT_NAME,
    DEFAULT_VOICE_NAME,
    DRIVETHRU_INSTRUCTIONS,
    build_voice_agent_definition,
    create_voice_agent,
    validate_voice_agent_definition,
)


class TestBuildVoiceAgentDefinition:
    def test_definition_has_voice_kind_and_managed_model(self):
        defn = build_voice_agent_definition(model="gpt-5.4", voice="en-US-Ava:DragonHDLatestNeural")

        assert defn["kind"] == "voice"
        assert defn["model_type"] == "managed"
        assert defn["model"] == "gpt-5.4"
        assert defn["instructions"] == DRIVETHRU_INSTRUCTIONS
        assert defn["output_modalities"] == ["text", "audio"]
        assert defn["tool_choice"] == "auto"
        assert defn["store"] is True

    def test_definition_audio_input_and_output_config(self):
        defn = build_voice_agent_definition()
        audio = defn["audio"]

        assert audio["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
        assert audio["input"]["transcription"] == {
            "model": "azure-speech",
            "language": "nl-NL,en-US",
        }
        assert audio["input"]["noise_reduction"] == {"type": "azure_deep_noise_suppression"}
        assert audio["input"]["turn_detection"]["type"] == "azure_semantic_vad"
        assert audio["output"]["format"] == {"type": "audio/pcm", "rate": 24000}
        assert audio["output"]["voice"] == DEFAULT_VOICE_NAME
        assert audio["output"]["voice_type"] == "azure-standard"

    def test_definition_serializes_all_drivethru_tools(self):
        defn = build_voice_agent_definition()
        tool_names = [t["name"] for t in defn["tools"]]

        assert tool_names == [
            "get_menu_items",
            "update_order_state",
            "submit_order",
            "get_order_analytics",
        ]
        for tool_dict in defn["tools"]:
            assert tool_dict["type"] == "function"
            assert "parameters" in tool_dict


class TestValidateVoiceAgentDefinition:
    def test_validates_matching_definition_allowing_service_defaults(self):
        expected = build_voice_agent_definition(model="gpt-5.4")
        observed = {
            **expected,
            "service_added_default": True,
            "audio": {
                "input": {
                    **expected["audio"]["input"],
                    "extra_server_flag": "enabled",
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "voice": {
                        "type": "azure-standard",
                        "name": DEFAULT_VOICE_NAME,
                    },
                },
            },
        }
        validate_voice_agent_definition(observed, expected)

    def test_raises_on_wrong_kind_or_model(self):
        expected = build_voice_agent_definition(model="gpt-5.4")
        bad_observed = {**expected, "kind": "prompt"}

        with pytest.raises(ValueError, match="Stored setting differs at definition.kind"):
            validate_voice_agent_definition(bad_observed, expected)


class TestAgentInstructionsAndTools:
    def test_all_tools_includes_update_order_state(self):
        tool_names = [t.name for t in ALL_TOOLS]
        assert "update_order_state" in tool_names
        assert "get_menu_items" in tool_names
        assert "submit_order" in tool_names
        assert "get_order_analytics" in tool_names

    def test_instructions_describe_guided_stages_and_flexibility(self):
        assert "update_order_state" in DRIVETHRU_INSTRUCTIONS
        assert "burgers" in DRIVETHRU_INSTRUCTIONS
        assert "sides" in DRIVETHRU_INSTRUCTIONS
        assert "drinks" in DRIVETHRU_INSTRUCTIONS
        assert "desserts" in DRIVETHRU_INSTRUCTIONS
        assert "review" in DRIVETHRU_INSTRUCTIONS


class TestCreateVoiceAgentLifecycle:
    def test_create_voice_agent_calls_enable_and_get_version(self, monkeypatch):
        monkeypatch.setenv("PROJECT_ENDPOINT", "https://mock-endpoint.services.ai.azure.com")

        mock_client = MagicMock()
        mock_agents = MagicMock()
        mock_client.agents = mock_agents

        mock_agent_version = MagicMock()
        mock_agent_version.name = AGENT_NAME
        mock_agent_version.version = "1"
        mock_agent_version.id = f"{AGENT_NAME}:1"
        mock_agents.create_version.return_value = mock_agent_version

        expected_def = build_voice_agent_definition()
        mock_readback = MagicMock()
        mock_readback.definition = expected_def
        mock_agents.get_version.return_value = mock_readback

        with patch("src.agents.create_voice_agent.DefaultAzureCredential"), \
             patch("src.agents.create_voice_agent.AIProjectClient", return_value=mock_client):
            mock_client.__enter__.return_value = mock_client
            res = create_voice_agent()

        mock_agents.enable.assert_called_once_with(AGENT_NAME)
        mock_agents.get_version.assert_called_once_with(
            agent_name=AGENT_NAME,
            agent_version="1",
        )
        assert res == {"name": AGENT_NAME, "version": "1", "id": f"{AGENT_NAME}:1"}

    def test_create_voice_agent_raises_runtime_error_when_readback_definition_missing(self, monkeypatch):
        monkeypatch.setenv("PROJECT_ENDPOINT", "https://mock-endpoint.services.ai.azure.com")

        mock_client = MagicMock()
        mock_agents = MagicMock()
        mock_client.agents = mock_agents

        mock_agent_version = MagicMock()
        mock_agent_version.name = AGENT_NAME
        mock_agent_version.version = "1"
        mock_agent_version.id = f"{AGENT_NAME}:1"
        mock_agents.create_version.return_value = mock_agent_version

        mock_readback = MagicMock(spec=[])  # no definition attribute
        mock_agents.get_version.return_value = mock_readback

        with patch("src.agents.create_voice_agent.DefaultAzureCredential"), \
             patch("src.agents.create_voice_agent.AIProjectClient", return_value=mock_client):
            mock_client.__enter__.return_value = mock_client
            with pytest.raises(RuntimeError, match=f"Voice Agent {AGENT_NAME} version 1"):
                create_voice_agent()

