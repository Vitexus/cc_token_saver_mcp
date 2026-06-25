# CC Token Saver MCP

Reduce your Claude Code token usage by delegating simple tasks to a local LLM.

The MCP server exposes your local LLM as tools that Claude Code can call for:

- Code snippet generation
- Simple refactoring
- Documentation writing
- Code reviews
- Basic Q&A

Claude Code routes simple, self-contained subtasks to the local LLM first,
only spending premium tokens on complex reasoning and multi-step workflows.

## Installation

### From Debian/Ubuntu package

```sh
apt install python3-cc-token-saver-mcp
```

### From source

```sh
pip install fastmcp openai python-dotenv
git clone https://github.com/Vitexus/cc_token_saver_mcp.git
```

## Configuration

### Local LLM

Create a `.env` file in the directory where you launch the server:

```ini
# Local LLM Configuration
OPENAI_API_KEY=none
OPENAI_BASE_URL=http://localhost:1234/v1
LOCAL_MODEL_NAME=qwen2.5-7b-instruct
LOCAL_LLM_TEMPERATURE=0.7
LOCAL_LLM_MAX_TOKENS=-1
```

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | `none` | Key sent to the local endpoint (usually ignored) |
| `OPENAI_BASE_URL` | `http://localhost:1234/v1` | OpenAI-compatible API base URL |
| `LOCAL_MODEL_NAME` | `qwen2.5-7b-instruct` | Model name to request |
| `LOCAL_LLM_TEMPERATURE` | `0.7` | Sampling temperature |
| `LOCAL_LLM_MAX_TOKENS` | `-1` | Max tokens per response (`-1` = no limit) |

### Claude Code MCP config

If installed from the Debian package, add to `~/.claude.json`:

```json
"mcpServers": {
  "cc-token-saver": {
    "type": "stdio",
    "command": "cc-token-saver-mcp"
  }
}
```

If running from source, point to `server.py` instead:

```json
"mcpServers": {
  "cc-token-saver": {
    "type": "stdio",
    "command": "python",
    "args": ["<path>/cc_token_saver_mcp/server.py"]
  }
}
```

## Tools

### `query_local_llm`

Send a prompt to the local LLM.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `prompt` | `str` | required | The user prompt |
| `system_message` | `str` | helpful assistant | System message |
| `temperature` | `float` | env default | Override temperature |
| `max_tokens` | `int` | env default | Override max tokens |

### `query_local_llm_with_context`

Send a prompt with additional context (e.g. a code snippet).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `prompt` | `str` | required | The task/question |
| `context` | `str` | required | Additional context |
| `task_type` | `str` | `general` | `code_review`, `documentation`, `refactor`, `general` |
| `system_message` | `str` | auto | Override system message |

## Example

<img width="1433" alt="cc-token_saver" src="https://github.com/user-attachments/assets/1e22553e-82bc-49c8-8ccd-5bd8b0306605" />

## License

MIT
