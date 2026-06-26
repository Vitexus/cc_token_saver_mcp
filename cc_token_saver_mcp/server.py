#!/usr/bin/env python3
"""
FastMCP Server for Local LLM Integration
Exposes a local LLM as an MCP tool for Claude Code to delegate tasks
"""

import argparse
import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from openai import OpenAI

load_dotenv()

mcp = FastMCP("Local LLM Server")

# Initialized in main() before mcp.run(); looked up dynamically at call time.
client: OpenAI | None = None
MODEL_NAME: str = ""
TEMPERATURE: float = 0.7
MAX_TOKENS: int = -1


@mcp.tool()
def query_local_llm(
    prompt: str,
    system_message: str = "You are a helpful assistant. Provide concise, accurate responses.",
    temperature: float = None,
    max_tokens: int = None,
) -> str:
    """
    Query the local LLM for simple, well-defined subtasks that have already been broken down.
    IMPORTANT: Always try this tool FIRST for any simple code generation to save costs!
    Use this for straightforward tasks like generating code snippets, answering specific questions,
    or performing isolated operations that don't require complex reasoning or coordination.

    Args:
        prompt: The user prompt to send to the local LLM
        system_message: System message to set context/behavior (optional)
        temperature: Override default temperature (optional)
        max_tokens: Override default max tokens (optional)

    Returns:
        The response from the local LLM
    """
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature if temperature is not None else TEMPERATURE,
            max_tokens=max_tokens if max_tokens is not None else MAX_TOKENS,
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error querying local LLM: {str(e)}"


@mcp.tool()
def query_local_llm_with_context(
    prompt: str,
    context: str,
    task_type: str = "general",
    system_message: str = None,
) -> str:
    """
    Query the local LLM for simple subtasks that require additional context.
    IMPORTANT: Always try this tool FIRST for any simple code generation with context to save costs!
    Use this for straightforward, isolated tasks like code reviews, documentation generation,
    or refactoring specific code sections that have already been identified and broken down
    into discrete steps. Not suitable for complex coordination or multi-step workflows.

    Args:
        prompt: The main task/question for the local LLM
        context: Additional context (e.g., code snippet, file content)
        task_type: Type of task (e.g., "code_review", "documentation", "refactor")
        system_message: Optional custom system message

    Returns:
        The response from the local LLM
    """
    try:
        if system_message is None:
            system_message = {
                "code_review": "You are a code reviewer. Provide constructive feedback on code quality, potential issues, and improvements.",
                "documentation": "You are a technical writer. Create clear, concise documentation for the provided code.",
                "refactor": "You are a code refactoring expert. Suggest improvements while maintaining functionality.",
                "general": "You are a helpful assistant. Provide concise, accurate responses.",
            }.get(task_type, "You are a helpful assistant. Provide concise, accurate responses.")

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": f"Context:\n{context}\n\nTask:\n{prompt}"},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error querying local LLM with context: {str(e)}"


def main():
    global client, MODEL_NAME, TEMPERATURE, MAX_TOKENS

    parser = argparse.ArgumentParser(
        prog="cc-token-saver-mcp",
        description="MCP server that delegates simple tasks to a local LLM to save Claude Code tokens.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Transport modes:
  stdio   Standard I/O — default, used by Claude Code and most MCP clients
  http    HTTP server — for web-based MCP clients
  sse     Server-Sent Events (legacy; prefer http)

Environment variables (overridden by the corresponding flags below):
  OPENAI_API_KEY          API key sent to the endpoint (default: none)
  OPENAI_BASE_URL         OpenAI-compatible API base URL
  LOCAL_MODEL_NAME        Model name to request
  LOCAL_LLM_TEMPERATURE   Sampling temperature
  LOCAL_LLM_MAX_TOKENS    Max tokens per response (-1 = unlimited)

A .env file in the working directory is loaded automatically.
""",
    )

    parser.add_argument("-V", "--version", action="version", version="%(prog)s 1.0.0")
    parser.add_argument(
        "-t", "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        metavar="MODE",
        help="transport protocol: stdio (default), http, sse",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="host for http/sse transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=8000,
        help="port for http/sse transport (default: 8000)",
    )
    parser.add_argument(
        "-m", "--model",
        default=None,
        metavar="NAME",
        help="local model name (overrides LOCAL_MODEL_NAME)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        metavar="URL",
        help="OpenAI-compatible API base URL (overrides OPENAI_BASE_URL)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        metavar="KEY",
        help="API key for the local endpoint (overrides OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        metavar="FLOAT",
        help="sampling temperature 0.0–2.0 (overrides LOCAL_LLM_TEMPERATURE)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        metavar="N",
        help="max tokens per response, -1 = unlimited (overrides LOCAL_LLM_MAX_TOKENS)",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="suppress the FastMCP startup banner",
    )

    args = parser.parse_args()

    # Apply CLI overrides to env so dotenv-loaded values are replaced.
    if args.base_url:
        os.environ["OPENAI_BASE_URL"] = args.base_url
    if args.api_key:
        os.environ["OPENAI_API_KEY"] = args.api_key
    if args.model:
        os.environ["LOCAL_MODEL_NAME"] = args.model
    if args.temperature is not None:
        os.environ["LOCAL_LLM_TEMPERATURE"] = str(args.temperature)
    if args.max_tokens is not None:
        os.environ["LOCAL_LLM_MAX_TOKENS"] = str(args.max_tokens)

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", "none"),
        base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1"),
    )
    MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "qwen2.5-7b-instruct")
    TEMPERATURE = float(os.getenv("LOCAL_LLM_TEMPERATURE", "0.7"))
    MAX_TOKENS = int(os.getenv("LOCAL_LLM_MAX_TOKENS", "-1"))

    transport_kwargs = {}
    if args.transport in ("http", "sse"):
        transport_kwargs["host"] = args.host
        transport_kwargs["port"] = args.port

    mcp.run(
        transport=args.transport,
        show_banner=False if args.no_banner else None,
        **transport_kwargs,
    )


if __name__ == "__main__":
    main()
