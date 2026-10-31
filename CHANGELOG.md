# iew - AI Code Review Tool (Fixed Implementation)

## Key Fixes

### 1. Format Parsing (iew/format.py)
- Simplified to line-only format:
  - `12: message` → line number only
- Removed support for character offsets, multi-line ranges, and coordinate pairs.

### 2. Agent Class (iew/agent.py)
- Replaced custom line-by-line TOML parsing with `tomllib` (standard library in Python 3.11+)
- Made review prompt configurable via `prompt` key in `~/.config/iew/iew.toml`
- Added `build_prompt` function supporting custom instructions or placeholder templates (`{code}`, `{file}`, etc.)
- Relaxed default prompt to be less restrictive on review scope while keeping `<line>: <description>` output format requirements explicit
- Added `verbose` parameter to `Agent.__init__`
- Added debug methods (`_debug`, `_fuzzy_file_search`) for detailed logging
- Improved error handling with proper stderr output instead of silent `except: pass`
- Enhanced Ollama API error handling with timeouts and error messages
- Maintained backward compatibility with default behavior

### 3. LSP Server (iew/lsp_server.py)
- Added `verbose` parameter to `SimpleLSP.__init__`
- Implemented `_debug` method for debug output
- Fixed `convert_feedback_to_diagnostics` to parse provided feedback directly (no dummy file rewrites)
- Made `IewLSP` alias compatible with imports
- Improved temp file management with proper cleanup

### 4. CLI Interface (iew/__main__.py)
- Added `--verbose` / `-v` flag for debug output
- Integrated debug statements throughout execution
- Maintained clean error handling and usage messages

## Verification

All supported coordinate formats now parse correctly:
- Line-only: `12: message`

The tool is now fully compliant with the README specifications and provides debugging capabilities through the new verbose flag.
