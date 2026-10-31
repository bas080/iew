# iew - AI Code Review Tool (Fixed Implementation)

## Key Fixes

### 1. Format Parsing (iew/format.py)
- Fixed parsing of all coordinate formats from README:
  - `12: message` → line number only
  - `45:2: message` → character offset
  - `78:0-78:15: message` → full coordinate pair (line, start_char, end_line, end_char)
  - `102-105: message` → multiline range without explicit line number
  - `150:0-150:8: message` → full coordinate pair with line number
  - `read: filename` → file read request
- All formats now parse correctly and match specification

### 2. Agent Class (iew/agent.py)
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
- Offset: `45:2: message`
- Pair: `78:0-78:15: message`, `150:0-150:8: message`
- Multiline range: `102-105: message`
- File read: `read: filename`

The tool is now fully compliant with the README specifications and provides debugging capabilities through the new verbose flag.