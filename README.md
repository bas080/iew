# iew

An AI-powered code review tool that integrates as a read-only LSP into your editor.

## What it does

- **Read-only**: Never mutates your code or filesystem.
- **LSP integration**: Works with editors that support LSP (VS Code, Neovim, etc.).
- **Lazy activation**: Only spins up when a file has been untouched for a while.
- **AI-powered feedback**: Uses Ollama to analyze code and generate structured feedback.
- **Simple line format**: Just a line number and message.

## iew-format

The feedback format uses coordinates to pinpoint issues:

```
12: Unused variable.
45: Missing quote.
78: Hardcoded secret.
102: Inefficient loop.
```

- `line: message` — a line-level issue

## Quick Start

### Install

```bash
pip install iew
```

### Usage

Run iew on a file to get feedback:

```bash
iew /path/to/file.js
```

### Features

- **AI enhancement** — uses Ollama to generate additional feedback
- **Configurable** — customize model, debounce, timeout, and review prompt via `~/.config/iew/iew.toml`

## Configuration

Configure iew in `~/.config/iew/iew.toml`:

```toml
model = "llama3"
debounce = 15
ollama_timeout = 180
keep_alive = "30m"   # Keep model & KV cache loaded in memory (e.g. "30m", "1h", "-1")

# Optional custom review prompt
prompt = "Review this code for bugs, logic errors, and performance improvements."
```

### Prompt Caching (KV Cache Optimization)

To minimize review latency on subsequent edits, iew formats prompts so all static instructions and output format rules are placed at the beginning:

1. **Global Static Header**: The review instructions and output rules match the cache across *all* files and requests.
2. **File & Code Prefix**: Subsequent reviews of the same file reuse the cached tokens from line 1 up to whichever line was modified.
3. **`keep_alive`**: Configured by default to keep the model and its KV cache resident in memory so subsequent edits don't trigger cold-reloads.

### Ollama Concurrency & Memory Tuning

When working across multiple files simultaneously, iew debounces edits per file and submits review requests to Ollama.

To allow Ollama to review multiple files concurrently, set `OLLAMA_NUM_PARALLEL`:

```bash
# In your ~/.bashrc (or systemd service environment)
export OLLAMA_NUM_PARALLEL=2
```

*(Restart your `ollama serve` instance after changing this variable.)*

#### Memory & Performance Considerations

- **Memory Usage**: Each parallel slot allocates its own KV-cache context window in addition to base model weights. Running a ~4B–7B parameter model with `OLLAMA_NUM_PARALLEL=2` can require 7–8+ GB of RAM or VRAM.
- **CPU vs. GPU**: On CPU-only setups, parallel generation divides CPU cores, increasing per-request review latency.
- **Tuning Tips**:
  - **16 GB RAM or CPU-only**: Use `OLLAMA_NUM_PARALLEL=1` or `2`. If experiencing high memory pressure or swap thrashing, increase `debounce` in `iew.toml` (e.g., `debounce = 30` or `45`) or use a lighter model (e.g., `qwen2.5-coder:3b-instruct` or `phi3`).
  - **Dedicated GPU (>= 16 GB VRAM)**: Parallel slots (`OLLAMA_NUM_PARALLEL=2` or higher) run with low latency.

## How it works

1. **Agent** reads the file and scans for issues
2. **Ollama** (via JSON API) provides AI-powered analysis
3. **Feedback** is formatted in iew-format and sent to the editor

## Requirements

- Python 3.8+
- Ollama running locally (default model: `llama3`)
- Editor supporting LSP (VS Code, Neovim, etc.)

## Testing

Run the test suite:

```bash
python3 -m pytest tests/ -v
```

All tests pass with Ollama running locally. See `TESTING.md` for detailed instructions and troubleshooting.

## License

MIT
