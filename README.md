# iew

An AI-powered code review tool that integrates as a read-only LSP into your editor.

## What it does

- **Read-only**: Never mutates your code or filesystem.
- **LSP integration**: Works with editors that support LSP (VS Code, Neovim, Helix, etc.).
- **Lazy activation**: Only spins up when a file has been untouched for a while.
- **AI-powered feedback**: Uses Ollama or OpenRouter to analyze code and generate structured feedback.
- **Simple line format**: Just a line number and message.

## Quick Start

### Install

```bash
pip install iew
```

Consult your code editor lsp config docs to start using iew in your editor.

### Testing the LSP Server

To debug the LSP server configuration, use the built-in health check command:

```bash
iew-lsp --health
```

This sends a "hi" message to your configured provider/model (e.g., Ollama) and shows where logs are stored. Example output:

```
Loaded config: provider=ollama, model=qwen2.5-coder:3b-instruct
Sending 'hi' to ollama model 'qwen2.5-coder:3b-instruct'...
Response: Hello! How can I assist you today?
Logs are stored in /home/bashbot/.config/iew/iew.log
```

## Configuration

Configure iew in `~/.config/iew/iew.toml` (or specify a custom path using `IEW_CONFIG` env var).

Request parameters sent to the model inference provider (Ollama / OpenRouter) are specified under the `[request]` table:

```toml
# Provider selection ("ollama" or "openrouter")
provider = "ollama"

# Common server settings
debounce = 15                       # Wait N seconds after typing stops before review
timeout = 180                       # Seconds to wait before timing out review request
log_file = "~/.config/iew/iew.log"  # Set to "/dev/null" to disable file logging
api_key = "sk-or-v1-..."            # OpenRouter API key (or set OPENROUTER_API_KEY env var)
max_retries = 3                     # HTTP retry attempts with exponential backoff

# Model inference request parameters (passed as-is to HTTP client)
[request]
model = "qwen2.5-coder:3b-instruct" # Model to use
keep_alive = "30m"                  # Ollama only: keep model & KV cache loaded
thinking = true                     # Enable reasoning/thinking mode (Ollama / OpenRouter)
prompt = "Review this code for bugs and logic errors." # Optional custom review prompt

# Any additional parameters under [request] are passed directly to the inference API:
# For Ollama: options = { temperature = 0.2, top_p = 0.9, seed = 42 }, system = "...", format = "json", etc.
# For OpenRouter: temperature = 0.3, max_tokens = 2000, top_p = 0.9, response_format = { type = "json_object" }, etc.
```

### Custom Config Path (`IEW_CONFIG`)

You can override the default configuration path by setting `IEW_CONFIG`:

```bash
export IEW_CONFIG=~/.config/iew/my-project.toml
```

## Requirements

- Python 3.8+
- Ollama running locally or an OpenRouter API key
- Editor supporting LSP (VS Code, Neovim, Helix, etc.)

## Testing

Run the test suite:

```bash
python3 -m pytest tests/ -v
```

## License

MIT
