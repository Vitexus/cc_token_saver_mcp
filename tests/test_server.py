"""
Tests for cc_token_saver_mcp.server

The server initialises client, MODEL_NAME, TEMPERATURE, and MAX_TOKENS lazily
inside main().  Unit tests inject them directly on the module; integration tests
point them at a real Ollama instance (localhost:11434).

Run all:              pytest tests/ -v
Run unit only:        pytest tests/ -v -m "not integration"
Run integration only: pytest tests/ -v -m integration
"""

import asyncio
import pytest
from unittest.mock import MagicMock
from openai import OpenAI

import cc_token_saver_mcp.server as srv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_client():
    """Replace the module-level client with a MagicMock and restore afterwards."""
    saved = (srv.client, srv.MODEL_NAME, srv.TEMPERATURE, srv.MAX_TOKENS)
    mc = MagicMock()
    srv.client = mc
    srv.MODEL_NAME = "test-model"
    srv.TEMPERATURE = 0.5
    srv.MAX_TOKENS = 100
    yield mc
    srv.client, srv.MODEL_NAME, srv.TEMPERATURE, srv.MAX_TOKENS = saved


@pytest.fixture()
def live_client():
    """Set server globals to use the local Ollama instance."""
    saved = (srv.client, srv.MODEL_NAME, srv.TEMPERATURE, srv.MAX_TOKENS)
    srv.client = OpenAI(api_key="none", base_url="http://localhost:11434/v1")
    srv.MODEL_NAME = "qwen2.5-coder:7b"
    srv.TEMPERATURE = 0.7
    srv.MAX_TOKENS = -1
    yield
    srv.client, srv.MODEL_NAME, srv.TEMPERATURE, srv.MAX_TOKENS = saved


# ---------------------------------------------------------------------------
# query_local_llm — unit tests
# ---------------------------------------------------------------------------

class TestQueryLocalLlm:

    def test_returns_llm_response(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("hello")
        assert srv.query_local_llm("say hello") == "hello"

    def test_default_params_from_globals(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.query_local_llm("test")
        kw = mock_client.chat.completions.create.call_args.kwargs
        assert kw["temperature"] == srv.TEMPERATURE  # 0.5 from fixture
        assert kw["max_tokens"] == srv.MAX_TOKENS    # 100 from fixture

    def test_override_temperature_and_max_tokens(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.query_local_llm("test", temperature=0.1, max_tokens=42)
        kw = mock_client.chat.completions.create.call_args.kwargs
        assert kw["temperature"] == 0.1
        assert kw["max_tokens"] == 42

    def test_default_system_message(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.query_local_llm("hi")
        msgs = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert msgs[0]["role"] == "system"
        assert "helpful assistant" in msgs[0]["content"].lower()

    def test_custom_system_message(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.query_local_llm("hi", system_message="You are a pirate.")
        msgs = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert msgs[0]["content"] == "You are a pirate."

    def test_user_prompt_in_messages(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.query_local_llm("what is 2+2?")
        msgs = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "what is 2+2?"

    def test_exception_returns_error_string(self, mock_client):
        mock_client.chat.completions.create.side_effect = Exception("connection refused")
        result = srv.query_local_llm("test")
        assert result.startswith("Error querying local LLM:")
        assert "connection refused" in result


# ---------------------------------------------------------------------------
# query_local_llm_with_context — unit tests
# ---------------------------------------------------------------------------

class TestQueryLocalLlmWithContext:

    def test_context_and_prompt_assembled(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.query_local_llm_with_context("what does it do?", "def foo(): pass")
        msgs = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert "Context:\ndef foo(): pass" in msgs[1]["content"]
        assert "Task:\nwhat does it do?" in msgs[1]["content"]

    @pytest.mark.parametrize("task_type,keyword", [
        ("code_review",    "code reviewer"),
        ("documentation",  "technical writer"),
        ("refactor",       "refactoring"),
        ("general",        "helpful assistant"),
    ])
    def test_task_type_picks_system_message(self, mock_client, task_type, keyword):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.query_local_llm_with_context("task", "ctx", task_type=task_type)
        msgs = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert keyword in msgs[0]["content"].lower()

    def test_unknown_task_type_falls_back_to_general(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.query_local_llm_with_context("task", "ctx", task_type="nonexistent")
        msgs = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert "helpful assistant" in msgs[0]["content"].lower()

    def test_custom_system_message_overrides_task_type(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.query_local_llm_with_context(
            "task", "ctx", task_type="code_review",
            system_message="You are a rubber duck."
        )
        msgs = mock_client.chat.completions.create.call_args.kwargs["messages"]
        assert msgs[0]["content"] == "You are a rubber duck."

    def test_exception_returns_error_string(self, mock_client):
        mock_client.chat.completions.create.side_effect = RuntimeError("timeout")
        result = srv.query_local_llm_with_context("task", "ctx")
        assert result.startswith("Error querying local LLM with context:")
        assert "timeout" in result


# ---------------------------------------------------------------------------
# MCP registration smoke test
# ---------------------------------------------------------------------------

class TestMcpRegistration:

    def test_both_tools_registered(self):
        tools = asyncio.run(srv.mcp.list_tools())
        names = {t.name for t in tools}
        assert "query_local_llm" in names
        assert "query_local_llm_with_context" in names


# ---------------------------------------------------------------------------
# Integration tests — require Ollama at localhost:11434
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIntegration:

    def test_query_local_llm_live(self, live_client):
        result = srv.query_local_llm("Reply with only the word PONG.")
        assert isinstance(result, str)
        assert len(result) > 0
        assert not result.startswith("Error")

    def test_query_local_llm_with_context_live(self, live_client):
        result = srv.query_local_llm_with_context(
            prompt="What does the function return?",
            context="def add(a, b):\n    return a + b",
            task_type="code_review",
        )
        assert isinstance(result, str)
        assert len(result) > 0
        assert not result.startswith("Error")
