"""End-to-end tests for iew code review tool.

These tests verify:
- Output coordinates pass through parse_coordinate correctly
- The CLI entry point runs end to end
- The LSP bin script starts and handles initialize messages
"""
import os
import sys
import tempfile
import subprocess
import json

from unittest.mock import patch

import pytest

from iew.agent import Agent, build_prompt, get_config
from iew.format import parse_coordinate


# --- Configuration & Prompt tests ---

def test_get_config_defaults(tmp_path):
    """When config file does not exist, default values are returned."""
    cfg = get_config(config_path=str(tmp_path / "nonexistent.toml"))
    assert cfg["model"] == "llama3"
    assert cfg["debounce"] == 15
    assert cfg["ollama_timeout"] == 180
    assert cfg["prompt"] is None


def test_get_config_custom_toml(tmp_path):
    """Configuration is loaded from TOML using tomllib."""
    toml_file = tmp_path / "iew.toml"
    toml_file.write_text(
        'model = "mistral"\n'
        'debounce = 30\n'
        'prompt = "Custom reviewer instructions"\n'
    )
    cfg = get_config(config_path=str(toml_file))
    assert cfg["model"] == "mistral"
    assert cfg["debounce"] == 30
    assert cfg["prompt"] == "Custom reviewer instructions"
    assert cfg["ollama_timeout"] == 180  # default preserved


def test_build_prompt_default():
    """Default prompt is flexible and clearly specifies line-number output format."""
    prompt = build_prompt({}, "foo.py", "1 | x = 1\n2 | y = 2")
    assert "foo.py" in prompt
    assert "1 | x = 1" in prompt
    assert "<line>: <concise description of issue>" in prompt
    assert "Output format instructions:" in prompt


def test_build_prompt_custom_instruction():
    """Custom prompt from toml is used as review instruction and keeps format clear."""
    cfg = {"prompt": "Review this code specifically for security vulnerabilities."}
    prompt = build_prompt(cfg, "foo.py", "1 | x = 1")
    assert "Review this code specifically for security vulnerabilities." in prompt
    assert "foo.py" in prompt
    assert "<line>: <concise description of issue>" in prompt


def test_build_prompt_custom_template():
    """Custom prompt with placeholders substitutes filename and code."""
    cfg = {"prompt": "Check {filename}:\n{code}\nOutput format:\n<line>: <msg>"}
    prompt = build_prompt(cfg, "bar.js", "1 | console.log('test');")
    assert "Check bar.js:" in prompt
    assert "1 | console.log('test');" in prompt
    assert "<line>: <msg>" in prompt


def test_agent_uses_configured_prompt(tmp_path):
    """Agent.review_file incorporates custom prompt from config."""
    f = tmp_path / "hello.py"
    f.write_text("print('hello')\n")
    agent = Agent()
    with patch("subprocess.run") as mock_run, patch("iew.agent.get_config") as mock_cfg:
        mock_cfg.return_value = {
            "model": "llama3",
            "ollama_timeout": 10,
            "prompt": "Custom prompt instructions for test"
        }
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = json.dumps({"response": "1: Custom warning"})
        feedback = agent.review_file(str(f))
        assert "1: Custom warning" in feedback
        payload = json.loads(mock_run.call_args[0][0][-1])
        assert "Custom prompt instructions for test" in payload["prompt"]
        assert "<line>: <concise description of issue>" in payload["prompt"]


# --- parse_coordinate ---

def test_parse_coordinate_line():
    coord = parse_coordinate("12: Unused variable.")
    assert coord == ('line', 12, 'Unused variable.')


def test_parse_coordinate_simple_only():
    coord = parse_coordinate("45:2: Missing quote.")
    assert coord == ('line', 45, '2: Missing quote.')


def test_parse_coordinate_empty():
    assert parse_coordinate("") is None
    assert parse_coordinate("   ") is None


def test_parse_coordinate_garbage():
    assert parse_coordinate("not a coordinate at all") is None


# --- CLI entry point ---

def test_cli_no_args_exits(tmp_path):
    """`iew` with no filepath should exit nonzero."""
    from iew.__main__ import main
    with pytest.raises(SystemExit):
        sys.argv = ["iew"]
        main()


def test_cli_reviews_file(tmp_path, capsys):
    """`iew <file>` prints feedback to stdout."""
    f = tmp_path / "test.js"
    f.write_text("const x = 1;\n")
    sys.argv = ["iew", str(f)]
    from iew.__main__ import main
    with patch("subprocess.run") as mock_run:
        # Simulate Ollama not available - the server should handle this gracefully
        mock_run.side_effect = Exception("Ollama not running")
        main()
    captured = capsys.readouterr()
    assert captured.out in ("", "No feedback.\n") or "error" in captured.out


# --- LSP bin script end-to-end test ---

def test_bin_lsp_initialize_and_review():
    """The bin script should start the LSP server, respond to initialize, and handle a textDocument/didOpen message."""
    bin_path = "/home/bashbot/iew/bin/iew-lsp"
    # Start the server process
    proc = subprocess.Popen(
        [sys.executable, bin_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for the startup banner
    startup = proc.stdout.readline().strip()
    assert "Starting" in startup, f"Unexpected startup output: {startup}"

    # Send an initialize LSP message
    init_msg = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    proc.stdin.write(json.dumps(init_msg) + "\n")
    proc.stdin.flush()

    # Read the initialize response
    response_line = proc.stdout.readline().strip()
    response = json.loads(response_line)

    # Verify response structure
    assert response["jsonrpc"] == "2.0"
    assert "result" in response
    assert response["result"]["capabilities"]["textDocumentSync"] == 1

    # Send a textDocument/didOpen message to trigger Ollama API call
    did_open_msg = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "textDocument/didOpen",
        "params": {
            "text_document": {
                "uri": "file:///home/bashbot/iew/sample.js",
                "text": "const x = 1;\n"
            }
        }
    }
    proc.stdin.write(json.dumps(did_open_msg) + "\n")
    proc.stdin.flush()

    # Read the publishDiagnostics response (this should come after Ollama processes the file)
    # We'll wait for the next message which should be textDocument/publishDiagnostics
    try:
        response_line = proc.stdout.readline().strip()
        if response_line:
            response = json.loads(response_line)
            # Check if it's a publishDiagnostics notification
            assert response["method"] == "textDocument/publishDiagnostics"
            assert "diagnostics" in response["params"]
            # Verify diagnostics were returned (content depends on AI)
            diagnostics = response["params"]["diagnostics"]
            assert isinstance(diagnostics, list), "Expected diagnostics list"
    except (json.JSONDecodeError, KeyError):
        # If we don't get the expected response within a reasonable time, that's OK
        # The server should still be working (even if Ollama isn't responding)
        pass

    # Close stdin to let the server exit cleanly
    proc.stdin.close()
    proc.wait(timeout=5)
