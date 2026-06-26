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
# list_available_models — unit tests
# ---------------------------------------------------------------------------

class TestListAvailableModels:

    def test_returns_model_list(self, mock_client):
        m1, m2 = MagicMock(), MagicMock()
        m1.id = "model-a"
        m2.id = "model-b"
        mock_client.models.list.return_value.data = [m1, m2]
        result = srv.list_available_models()
        assert "model-a" in result
        assert "model-b" in result

    def test_exception_returns_error_string(self, mock_client):
        mock_client.models.list.side_effect = Exception("unreachable")
        result = srv.list_available_models()
        assert result.startswith("Error listing models:")


# ---------------------------------------------------------------------------
# switch_model — unit tests
# ---------------------------------------------------------------------------

class TestSwitchModel:

    def test_switches_global_model_name(self, mock_client):
        srv.MODEL_NAME = "old-model"
        result = srv.switch_model("new-model")
        assert srv.MODEL_NAME == "new-model"
        assert "new-model" in result

    def test_confirmation_includes_old_name(self, mock_client):
        srv.MODEL_NAME = "old-model"
        result = srv.switch_model("new-model")
        assert "old-model" in result


# ---------------------------------------------------------------------------
# summarize_text — unit tests
# ---------------------------------------------------------------------------

class TestSummarizeText:

    def test_returns_summary(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("A short summary.")
        result = srv.summarize_text("Long text here...")
        assert result == "A short summary."

    def test_max_words_in_prompt(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.summarize_text("text", max_words=50)
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "50" in prompt

    def test_focus_included_in_prompt(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.summarize_text("text", focus="security issues")
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "security issues" in prompt

    def test_exception_returns_error_string(self, mock_client):
        mock_client.chat.completions.create.side_effect = Exception("timeout")
        assert srv.summarize_text("text").startswith("Error summarizing text:")


# ---------------------------------------------------------------------------
# generate_commit_message — unit tests
# ---------------------------------------------------------------------------

class TestGenerateCommitMessage:

    def test_returns_commit_message(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("feat: add login")
        result = srv.generate_commit_message("diff --git a/x.py ...")
        assert result == "feat: add login"

    def test_diff_in_user_prompt(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.generate_commit_message("my diff content")
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "my diff content" in prompt

    def test_extra_context_included(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.generate_commit_message("diff", extra_context="fixes #99")
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "fixes #99" in prompt

    def test_exception_returns_error_string(self, mock_client):
        mock_client.chat.completions.create.side_effect = Exception("err")
        assert srv.generate_commit_message("diff").startswith("Error generating commit message:")


# ---------------------------------------------------------------------------
# generate_unit_tests — unit tests
# ---------------------------------------------------------------------------

class TestGenerateUnitTests:

    def test_returns_test_code(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("def test_foo(): pass")
        result = srv.generate_unit_tests("def foo(): return 1")
        assert "test_foo" in result

    def test_framework_in_system_message(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.generate_unit_tests("code", framework="unittest")
        sys_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "unittest" in sys_msg

    def test_extra_instructions_in_prompt(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.generate_unit_tests("code", extra_instructions="cover None input")
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "cover None input" in prompt

    def test_exception_returns_error_string(self, mock_client):
        mock_client.chat.completions.create.side_effect = Exception("err")
        assert srv.generate_unit_tests("code").startswith("Error generating unit tests:")


# ---------------------------------------------------------------------------
# explain_code — unit tests
# ---------------------------------------------------------------------------

class TestExplainCode:

    def test_returns_explanation(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("It adds two numbers.")
        result = srv.explain_code("def add(a, b): return a + b")
        assert result == "It adds two numbers."

    @pytest.mark.parametrize("audience,keyword", [
        ("beginner", "jargon"),
        ("developer", "developer"),
        ("expert", "expert"),
    ])
    def test_audience_affects_system_message(self, mock_client, audience, keyword):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.explain_code("code", audience=audience)
        sys_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"].lower()
        assert keyword in sys_msg

    def test_unknown_audience_falls_back_to_developer(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.explain_code("code", audience="alien")
        sys_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"].lower()
        assert "developer" in sys_msg

    def test_exception_returns_error_string(self, mock_client):
        mock_client.chat.completions.create.side_effect = Exception("err")
        assert srv.explain_code("code").startswith("Error explaining code:")


# ---------------------------------------------------------------------------
# translate_text — unit tests
# ---------------------------------------------------------------------------

class TestTranslateText:

    def test_returns_translation(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("Ahoj světe")
        result = srv.translate_text("Hello world", "Czech")
        assert result == "Ahoj světe"

    def test_target_language_in_prompt(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.translate_text("hello", "German")
        prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        assert "German" in prompt

    def test_formatting_note_when_preserve_true(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.translate_text("text", "Czech", preserve_formatting=True)
        sys_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "markdown" in sys_msg.lower()

    def test_no_formatting_note_when_preserve_false(self, mock_client):
        mock_client.chat.completions.create.return_value = _mock_response("ok")
        srv.translate_text("text", "Czech", preserve_formatting=False)
        sys_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert "markdown" not in sys_msg.lower()

    def test_exception_returns_error_string(self, mock_client):
        mock_client.chat.completions.create.side_effect = Exception("err")
        assert srv.translate_text("text", "Czech").startswith("Error translating text:")


# ---------------------------------------------------------------------------
# MCP registration smoke test
# ---------------------------------------------------------------------------

class TestMcpRegistration:

    def test_all_tools_registered(self):
        tools = asyncio.run(srv.mcp.list_tools())
        names = {t.name for t in tools}
        expected = {
            "query_local_llm",
            "query_local_llm_with_context",
            "list_available_models",
            "switch_model",
            "summarize_text",
            "generate_commit_message",
            "generate_unit_tests",
            "explain_code",
            "translate_text",
        }
        assert expected == names


# ---------------------------------------------------------------------------
# Integration tests — require Ollama at localhost:11434
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIntegration:

    def test_query_local_llm_live(self, live_client):
        result = srv.query_local_llm("Reply with only the word PONG.")
        assert isinstance(result, str) and len(result) > 0
        assert not result.startswith("Error")

    def test_query_local_llm_with_context_live(self, live_client):
        result = srv.query_local_llm_with_context(
            prompt="What does the function return?",
            context="def add(a, b):\n    return a + b",
            task_type="code_review",
        )
        assert isinstance(result, str) and len(result) > 0
        assert not result.startswith("Error")

    def test_list_available_models_live(self, live_client):
        result = srv.list_available_models()
        assert "qwen" in result.lower()
        assert not result.startswith("Error")

    def test_summarize_text_live(self, live_client):
        result = srv.summarize_text(
            "Python is a high-level, general-purpose programming language. "
            "Its design philosophy emphasises code readability. "
            "It supports multiple programming paradigms.",
            max_words=30,
        )
        assert isinstance(result, str) and len(result) > 0
        assert not result.startswith("Error")

    def test_generate_commit_message_live(self, live_client):
        result = srv.generate_commit_message(
            "diff --git a/server.py b/server.py\n+def new_tool(): pass"
        )
        assert isinstance(result, str) and len(result) > 0
        assert not result.startswith("Error")

    def test_explain_code_live(self, live_client):
        result = srv.explain_code("def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)")
        assert isinstance(result, str) and len(result) > 0
        assert not result.startswith("Error")

    def test_translate_text_live(self, live_client):
        result = srv.translate_text("Hello, how are you?", "Czech")
        assert isinstance(result, str) and len(result) > 0
        assert not result.startswith("Error")
