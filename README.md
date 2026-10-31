# iew

An AI-powered code review tool that integrates as a read-only LSP into your editor.

## What it does

- **Read-only**: Never mutates your code or filesystem.
- **LSP integration**: Works with editors that support LSP (VS Code, Neovim, etc.).
- **Lazy activation**: Only spins up when a file has been untouched for a while.
- **AI-powered feedback**: Uses Ollama to analyze code and generate structured feedback.
- **Multi-format support**: Handles line-only, single-line offsets, multi-line ranges, and full coordinate pairs.
- **TODO detection** — finds TODO comments in the code
- **Read requests** — `read: other.js` requests other files for context and does a fuzzy search on file names. (first n results) We do not want to overwhelm the AI by sending a bunch of file contents.

## iew-format

The feedback format uses coordinates to pinpoint issues:

```
12: Unused variable.
45:2: Missing quote.
78:0-78:15: Hardcoded secret.
102-105: Inefficient loop.
150:0-150:8: Error handling missing.
read: main.mjs
read: substring match
```

- `line: message` — a line-level issue
- `offset: line:char: message` — a character offset within a line
- `range: start-end: message` — a multi-line range
- `pair: line:start-end: message` — full coordinate pair
- `read: filename` — a request to read another file

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

- **TODO detection** — finds TODO comments in the code
- **Read requests** — `read: other.js` requests other files for context and does a fuzzy search on file names. (first n results) We do not want to overwhelm the AI by sending a bunch of file contents.
- **AI enhancement** — uses Ollama to generate additional feedback

## How it works

1. **Agent** reads the file and scans for issues (TODO, read requests, etc.)
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