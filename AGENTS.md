# AGENTS.md — CC Token Saver MCP

## Purpose

This repository contains the **CC Token Saver MCP** server — an MCP
(Model Context Protocol) server that proxies requests from Claude Code to a
locally running LLM. Its goal is to reduce expensive API token usage by
handling simple, self-contained subtasks locally.

## Repository Layout

```
cc_token_saver_mcp/   Python package (importable module)
  __init__.py
  server.py           FastMCP server with tool definitions and main()
server.py             Backwards-compatible entry point (delegates to package)
debian/               Debian packaging (control, rules, changelog, Jenkinsfile…)
  cc-token-saver-mcp.1                    Man page (troff format)
  cz.vitexsoftware.cc-token-saver-mcp.metainfo.xml  AppStream metadata
  cz.vitexsoftware.cc-token-saver-mcp.svg            Application icon
pyproject.toml        Build definition (setuptools, console script entry point)
requirements.txt      Pinned runtime deps for development / pip install
.env.example          Template for local LLM configuration
```

## Tools Exposed by the MCP Server

| Tool | When to call |
|---|---|
| `query_local_llm` | Simple prompts with no surrounding context |
| `query_local_llm_with_context` | Prompts that need a code snippet or text block as context |
| `list_available_models` | Discover which models are loaded at the local endpoint |
| `switch_model` | Change the active model for subsequent calls in the session |
| `summarize_text` | Condense long texts, logs, or READMEs to save context tokens |
| `generate_commit_message` | Produce a Conventional Commits message from `git diff --staged` |
| `generate_unit_tests` | Generate boilerplate tests (pytest, unittest, jest, go test, …) |
| `explain_code` | Plain-language explanation at beginner / developer / expert level |
| `translate_text` | Translate text to another language, preserving markdown structure |

All tools are decorated with `@mcp.tool()` in `cc_token_saver_mcp/server.py`.

## Adding a New Tool

1. Open `cc_token_saver_mcp/server.py`.
2. Define a new function decorated with `@mcp.tool()`.
3. Return a plain string — FastMCP serialises it automatically.
4. Update `debian/cc-token-saver-mcp.1` (TOOLS EXPOSED section) and `README.md`.

## Running Locally

```sh
cp .env.example .env        # fill in your local LLM details
pip install -e .
cc-token-saver-mcp
```

Or without installing:

```sh
python cc_token_saver_mcp/server.py
```

## Environment Variables

See `.env.example` for the full list. The server reads them at startup via
`python-dotenv`; any variable can also be set in the shell environment to
override the `.env` file.

## Debian Package

Binary package: `python3-cc-token-saver-mcp`  
Build: `dpkg-buildpackage -us -uc -b` (or via the Jenkins pipeline)  
CI: `https://jenkins.proxy.spojenet.cz/job/Foregin/job/cc-token-saver-mcp/`

All three runtime dependencies (`fastmcp`, `openai`, `python-dotenv`) are
available in Debian/Ubuntu as `python3-fastmcp`, `python3-openai`,
`python3-dotenv`.

## Coding Conventions

- Python 3.10+, type hints on all tool parameters.
- No comments unless the reason is non-obvious.
- Tests are not currently packaged; skip them in the Debian build via
  `override_dh_auto_test` in `debian/rules`.
