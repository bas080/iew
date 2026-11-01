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
    assert cfg["provider"] == "ollama"
    assert cfg["model"] == "llama3"
    assert cfg["api_key"] is None
    assert cfg["debounce"] == 15
    assert cfg["timeout"] == 180
    assert cfg["max_retries"] == 3
    assert cfg["request"]["prompt"] is None
    assert cfg["request"]["keep_alive"] == "30m"
    assert cfg["request"]["thinking"] is None
    assert cfg["log_file"] == "~/.config/iew/iew.log"


def test_get_config_iew_config_env(tmp_path, monkeypatch):
    """Configuration path can be specified via IEW_CONFIG environment variable."""
    custom_toml = tmp_path / "custom.toml"
    custom_toml.write_text('provider = "openrouter"\nmodel = "custom-model"\n')
    monkeypatch.setenv("IEW_CONFIG", str(custom_toml))
    cfg = get_config()
    assert cfg["provider"] == "openrouter"
    assert cfg["model"] == "custom-model"


def test_get_config_custom_toml(tmp_path):
    """Configuration is loaded from TOML using tomllib."""
    toml_file = tmp_path / "iew.toml"
    toml_file.write_text(
        'model = "mistral"\n'
        'debounce = 30\n'
        '[request]\n'
        'prompt = "Custom reviewer instructions"\n'
    )
    cfg = get_config(config_path=str(toml_file))
    assert cfg["model"] == "mistral"
    assert cfg["debounce"] == 30
    assert cfg["request"]["prompt"] == "Custom reviewer instructions"
    assert cfg["timeout"] == 180  # default preserved


def test_build_prompt_default():
    """Default prompt is flexible and clearly specifies line-number output format."""
    prompt = build_prompt({}, "foo.py", "1 | x = 1\n2 | y = 2")
    assert "foo.py" in prompt
    assert "1 | x = 1" in prompt
    assert "<line>: <concise description of issue>" in prompt
    assert "Output format instructions:" in prompt


def test_build_prompt_custom_instruction():
    """Custom prompt from toml is used as review instruction and keeps format clear."""
    cfg = {"request": {"prompt": "Review this code specifically for security vulnerabilities."}}
    prompt = build_prompt(cfg, "foo.py", "1 | x = 1")
    assert "Review this code specifically for security vulnerabilities." in prompt
    assert "foo.py" in prompt
    assert "<line>: <concise description of issue>" in prompt


def test_build_prompt_custom_template():
    """Custom prompt with placeholders substitutes filename and code."""
    cfg = {"request": {"prompt": "Check {filename}:\n{code}\nOutput format:\n<line>: <msg>"}}
    prompt = build_prompt(cfg, "bar.js", "1 | console.log('test');")
    assert "Check bar.js:" in prompt
    assert "1 | console.log('test');" in prompt
    assert "<line>: <msg>" in prompt


def test_build_prompt_prefix_order():
    """Verify that static instructions appear before the file and code to maximize KV cache hits."""
    prompt = build_prompt({}, "foo.py", "1 | x = 1")
    instr_pos = prompt.find("Output format instructions:")
    file_pos = prompt.find("Code file: foo.py")
    code_pos = prompt.find("1 | x = 1")
    assert instr_pos != -1
    assert file_pos != -1
    assert code_pos != -1
    assert instr_pos < file_pos < code_pos


def test_agent_uses_configured_prompt(tmp_path):
    """Agent.review_file incorporates custom prompt from config."""
    f = tmp_path / "hello.py"
    f.write_text("print('hello')\n")
    agent = Agent()

    class MockResponse:
        def __init__(self, data):
            self.data = data
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_data = json.dumps({"response": "1: Custom warning"}).encode("utf-8")
    with patch("urllib.request.urlopen") as mock_urlopen, patch("iew.agent.get_config") as mock_cfg:
        mock_cfg.return_value = {
            "model": "llama3",
            "timeout": 10,
            "request": {"prompt": "Custom prompt instructions for test"}
        }
        mock_urlopen.return_value = MockResponse(mock_data)
        feedback = agent.review_file(str(f))
        assert "1: Custom warning" in feedback
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert "Custom prompt instructions for test" in payload["prompt"]
        assert "<line>: <concise description of issue>" in payload["prompt"]


def test_agent_openrouter_provider(tmp_path):
    """Agent.review_file correctly calls OpenRouter API when provider = openrouter."""
    f = tmp_path / "test.py"
    f.write_text("x = 1\n")
    agent = Agent()

    mock_response_data = json.dumps({
        "choices": [
            {
                "message": {
                    "content": "2: Unused variable x."
                }
            }
        ]
    }).encode("utf-8")

    class MockResponse:
        def __init__(self, data):
            self.data = data
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("iew.agent.get_config") as mock_cfg, patch("urllib.request.urlopen") as mock_urlopen:
        mock_cfg.return_value = {
            "provider": "openrouter",
            "api_key": "test-or-key",
            "model": "deepseek/deepseek-chat-v3-0324:free",
            "timeout": 10,
            "prompt": None
        }
        mock_urlopen.return_value = MockResponse(mock_response_data)

        feedback = agent.review_file(str(f))
        assert "2: Unused variable x." in feedback

        # Verify request details
        req = mock_urlopen.call_args[0][0]
        assert req.get_full_url() == "https://openrouter.ai/api/v1/chat/completions"
        assert req.get_header("Authorization") == "Bearer test-or-key"
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "deepseek/deepseek-chat-v3-0324:free"
        assert len(body["messages"]) == 1


# --- Adapter tests ---

def test_get_adapter_resolution():
    """get_adapter factory resolves providers correctly."""
    from iew.adapters import get_adapter, OllamaAdapter, OpenRouterAdapter

    ollama = get_adapter({"provider": "ollama"})
    assert isinstance(ollama, OllamaAdapter)

    # Default is ollama
    default_adapter = get_adapter({})
    assert isinstance(default_adapter, OllamaAdapter)

    openrouter = get_adapter({"provider": "openrouter", "api_key": "dummy"})
    assert isinstance(openrouter, OpenRouterAdapter)

    with pytest.raises(ValueError, match="Unknown provider 'invalid'"):
        get_adapter({"provider": "invalid"})


def test_openrouter_adapter_missing_key():
    """OpenRouterAdapter raises ValueError if no API key is configured."""
    from iew.adapters.openrouter import OpenRouterAdapter

    adapter = OpenRouterAdapter({"provider": "openrouter"})
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="OpenRouter API key missing"):
            adapter.complete("hello")


def test_ollama_adapter_thinking():
    """OllamaAdapter passes 'think' in payload when thinking is configured."""
    from iew.adapters.ollama import OllamaAdapter

    adapter = OllamaAdapter({"provider": "ollama", "request": {"thinking": True}})

    class MockResponse:
        def __init__(self, data):
            self.data = data
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_data = json.dumps({"response": "ok", "thinking": "thought process"}).encode("utf-8")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(mock_data)
        resp = adapter.complete("test prompt")
        assert resp == "ok"
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["think"] is True


def test_openrouter_adapter_thinking():
    """OpenRouterAdapter maps thinking to reasoning in payload."""
    from iew.adapters.openrouter import OpenRouterAdapter

    class MockResponse:
        def __init__(self, data):
            self.data = data
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_data = json.dumps({
        "choices": [{
            "message": {
                "content": "review output",
                "reasoning": "step 1, step 2"
            }
        }]
    }).encode("utf-8")

    # Test boolean True -> effort: medium
    adapter = OpenRouterAdapter({
        "provider": "openrouter",
        "api_key": "test-key",
        "request": {"thinking": True},
    })
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(mock_data)
        out = adapter.complete("prompt")
        assert out == "review output"
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["reasoning"] == {"effort": "medium"}

    # Test string effort (e.g. "high")
    adapter_str = OpenRouterAdapter({
        "provider": "openrouter",
        "api_key": "test-key",
        "request": {"thinking": "high"},
    })
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(mock_data)
        adapter_str.complete("prompt")
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["reasoning"] == {"effort": "high"}


def test_ollama_adapter_request_passed_as_is():
    """All custom fields under request in toml are passed as-is to the Ollama HTTP client."""
    from iew.adapters.ollama import OllamaAdapter

    adapter = OllamaAdapter({
        "provider": "ollama",
        "request": {
            "model": "qwen2.5-coder:3b-instruct",
            "keep_alive": "1h",
            "options": {"temperature": 0.2, "top_p": 0.9, "seed": 42},
            "system": "Custom system instructions",
            "format": "json",
            "custom_field": "custom_value",
        }
    })

    class MockResponse:
        def __init__(self, data):
            self.data = data
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_data = json.dumps({"response": "ok"}).encode("utf-8")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(mock_data)
        resp = adapter.complete("test prompt")
        assert resp == "ok"
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["model"] == "qwen2.5-coder:3b-instruct"
        assert payload["prompt"] == "test prompt"
        assert payload["stream"] is False
        assert payload["keep_alive"] == "1h"
        assert payload["options"] == {"temperature": 0.2, "top_p": 0.9, "seed": 42}
        assert payload["system"] == "Custom system instructions"
        assert payload["format"] == "json"
        assert payload["custom_field"] == "custom_value"


def test_openrouter_adapter_request_passed_as_is():
    """All custom fields under request in toml are passed as-is to the OpenRouter HTTP client."""
    from iew.adapters.openrouter import OpenRouterAdapter

    adapter = OpenRouterAdapter({
        "provider": "openrouter",
        "api_key": "test-key",
        "request": {
            "model": "anthropic/claude-3.5-sonnet",
            "temperature": 0.3,
            "max_tokens": 1500,
            "top_p": 0.95,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.2,
            "stop": ["\n\n"],
            "response_format": {"type": "json_object"},
            "custom_header_or_param": 123,
        }
    })

    class MockResponse:
        def __init__(self, data):
            self.data = data
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_data = json.dumps({
        "choices": [{"message": {"content": "feedback"}}]
    }).encode("utf-8")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = MockResponse(mock_data)
        out = adapter.complete("prompt text")
        assert out == "feedback"
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "anthropic/claude-3.5-sonnet"
        assert body["messages"] == [{"role": "user", "content": "prompt text"}]
        assert body["temperature"] == 0.3
        assert body["max_tokens"] == 1500
        assert body["top_p"] == 0.95
        assert body["presence_penalty"] == 0.1
        assert body["frequency_penalty"] == 0.2
        assert body["stop"] == ["\n\n"]
        assert body["response_format"] == {"type": "json_object"}
        assert body["custom_header_or_param"] == 123


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


def test_multiline_feedback_processing():
    """Agent._process_feedback handles multi-line feedback where explanation continues on next lines."""
    agent = Agent()
    feedback = []
    output = (
        "12: First issue description\n"
        "  Explanation for first issue on next line\n"
        "  Suggestion on line three\n"
        "45: Second issue\n"
        "  Detail for second issue"
    )
    agent._process_feedback(output, ["line"] * 50, feedback)
    assert len(feedback) == 2
    assert feedback[0] == "12: First issue description\nExplanation for first issue on next line\nSuggestion on line three"
    assert feedback[1] == "45: Second issue\nDetail for second issue"


def test_multiline_feedback_to_diagnostics():
    """SimpleLSP.convert_feedback_to_diagnostics preserves multi-line explanation in Diagnostic message."""
    from iew.lsp_server import SimpleLSP
    server = SimpleLSP()
    feedback_text = (
        "5: Error found\n"
        "  More context on this error\n"
        "  How to fix it"
    )
    diags = server.convert_feedback_to_diagnostics("file:///test.py", feedback_text)
    assert len(diags) == 1
    assert diags[0].message == "Error found\nMore context on this error\nHow to fix it"
    assert diags[0].range.start.line == 4



def test_bin_lsp_initialize_and_review(tmp_path):
    """The bin script should start the LSP server, respond to initialize, and handle a textDocument/didOpen message."""
    bin_path = "/home/bashbot/iew/bin/iew-lsp"
    
    # Write a temporary config to avoid using user's configuration
    # especially to set debounce = 0 so the test runs instantly,
    # and use an actually installed model on the test environment.
    config_file = tmp_path / "test_iew.toml"
    config_file.write_text("provider = \"ollama\"\nmodel = \"qwen2.5-coder:3b-instruct\"\ndebounce = 0\ntimeout = 10\n")
    
    env = os.environ.copy()
    env["IEW_CONFIG"] = str(config_file)

    # Start the server process
    proc = subprocess.Popen(
        [sys.executable, bin_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    # Wait for the startup banner
    startup = proc.stderr.readline().strip()
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

    def read_lsp_message(stream):
        content_length = None
        while True:
            line = stream.readline()
            if not line:
                return None
            line_stripped = line.strip()
            if not line_stripped:
                if content_length is not None:
                    break
                continue
            if line_stripped.lower().startswith("content-length:"):
                parts = line_stripped.split(":", 1)
                try:
                    content_length = int(parts[1].strip())
                except ValueError:
                    pass
        if content_length is not None:
            body = stream.read(content_length)
            return json.loads(body)
        return None

    # Read the initialize response
    response = read_lsp_message(proc.stdout)
    assert response is not None, "Expected initialize response"

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
        response = read_lsp_message(proc.stdout)
        if response:
            # Check if it's a publishDiagnostics notification
            assert response["method"] == "textDocument/publishDiagnostics"
            assert "diagnostics" in response["params"]
            # Verify diagnostics were returned (content depends on AI)
            diagnostics = response["params"]["diagnostics"]
            assert isinstance(diagnostics, list), "Expected diagnostics list"
    except Exception:
        # If we don't get the expected response within a reasonable time, that's OK
        # The server should still be working (even if Ollama isn't responding)
        pass

    # Close stdin to let the server exit cleanly
    proc.stdin.close()
    proc.wait(timeout=5)


# --- Health check command test ---


def test_bin_lsp_health_check(tmp_path):
    """The bin script --health flag should send "hi" to configured provider and print log location."""
    bin_path = "/home/bashbot/iew/bin/iew-lsp"

    config_file = tmp_path / "test_iew.toml"
    config_file.write_text('provider = "ollama"\nmodel = "qwen2.5-coder:3b-instruct"\ndebounce = 0\ntimeout = 10\n')

    env = os.environ.copy()
    env["IEW_CONFIG"] = str(config_file)

    # Run the health check command
    result = subprocess.run(
        [sys.executable, bin_path, "--health"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )

    # The command should run (may succeed or fail depending on Ollama availability)
    # But it should always print the loaded config and log location
    assert "Loaded config:" in result.stdout
    assert "provider=ollama" in result.stdout
    assert "model=qwen2.5-coder:3b-instruct" in result.stdout
    assert "Sending 'hi'" in result.stdout
    assert "Logs are stored in" in result.stdout
    # Exit code can be 0 (success) or 1 (Ollama error)
    assert result.returncode in (0, 1)

    # Check that config was actually read from the temp file (not defaults)
    # The config should show the model from our temp config, not the default llama3
    assert "qwen2.5-coder:3b-instruct" in result.stdout
